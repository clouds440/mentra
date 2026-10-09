import { chooseOption } from './select-helpers';
import { expect, test } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { finishOnboardingWithoutAssessment } from './profile-helpers';

async function register(page: import('@playwright/test').Page) {
  await page.goto('/register');
  await page.getByLabel('Username', { exact:true }).fill(`learning_${randomUUID().slice(0,8)}`);
  await page.getByLabel('Password', { exact:true }).fill('an isolated learning workflow password');
  await page.getByRole('button',{name:'Create account',exact:true}).click();
  await finishOnboardingWithoutAssessment(page);
}

test('event proposal recovers in Progress and commits once',async({page})=>{
  await register(page);
  await page.getByRole('textbox',{name:'Ask Mentra anything'}).fill('My algebra exam is on October 20.');
  await page.getByRole('button',{name:'Send message'}).click();
  await expect(page.getByRole('region',{name:'Event proposal'})).toBeVisible();
  await page.goto('/progress?tab=events');
  const proposal=page.getByRole('region',{name:'Event proposal'});
  await expect(proposal.getByRole('heading',{name:'Algebra exam'})).toBeVisible();
  await proposal.getByRole('button',{name:'Add event',exact:true}).click();
  await page.getByRole('button',{name:'Check dates & reminder'}).click();
  await page.getByRole('button',{name:'Save event',exact:true}).click();
  await expect(proposal.getByText('Event saved.',{exact:true})).toBeVisible();
  await proposal.getByRole('link',{name:'View event',exact:true}).click();
  await expect(page.getByRole('region',{name:'Event details'}).getByRole('heading',{name:'Algebra exam'})).toBeVisible();
});

test('assessment grading, correction, paper confirmation and learning progress',async({page})=>{
  test.setTimeout(60_000);
  await register(page);
  const response=await page.request.post('http://127.0.0.1:18003/api/v1/learning-contexts',{headers:{Origin:'http://127.0.0.1:15173'},data:{name:'Algebra',activate:true}});
  expect(response.ok()).toBeTruthy();const context=await response.json();
  await page.getByRole('link',{name:'Assessments',exact:true}).click();
  await page.getByRole('button',{name:'Create assessment',exact:true}).click();
  await chooseOption(page.getByLabel('Assessment learning context',{exact:true}), context.context_id);
  await page.getByLabel('Topic',{exact:true}).fill('Linear equations');
  await page.getByLabel('Concept names (comma separated, optional)',{exact:true}).fill('Linear equations');
  await page.getByLabel('Confirm these names as new learning concepts if needed').check();
  await page.getByLabel('Question count',{exact:true}).fill('2');
  await page.getByRole('button',{name:'Generate assessment',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Practice: Linear equations',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Start new attempt',exact:true}).click();
  await page.getByLabel('Answer 1',{exact:true}).fill('First partial explanation.');
  await page.getByLabel('Answer 2',{exact:true}).fill('Second partial explanation.');
  await page.getByRole('button',{name:'Submit answers',exact:true}).click();
  await expect(page.getByText('Feedback saved and learner evidence applied.',{exact:true})).toBeVisible({timeout:20_000});
  await page.getByRole('button',{name:'Correct answers or transcription',exact:true}).click();
  await page.getByLabel('Answer 1',{exact:true}).fill('A corrected explanation.');
  await page.getByRole('button',{name:'Submit answers',exact:true}).click();
  await expect(page.getByText('Feedback saved and learner evidence applied.',{exact:true})).toBeVisible({timeout:20_000});
  await expect(page.getByText('Previous grade revisions',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Start new attempt',exact:true}).click();
  await page.getByLabel('Upload assessment answer sheet',{exact:true}).setInputFiles({name:'answers.txt',mimeType:'text/plain',buffer:Buffer.from('1. First handwritten answer\n2. Second handwritten answer')});
  await expect(page.getByLabel('Answer 1',{exact:true})).toHaveValue('First handwritten answer');
  await expect(page.getByRole('button',{name:'Confirm text & submit',exact:true})).toBeDisabled();
  await page.getByLabel('I reviewed and corrected all extracted answers').check();
  await page.getByRole('button',{name:'Confirm text & submit',exact:true}).click();
  await expect(page.getByText('Feedback saved and learner evidence applied.',{exact:true})).toBeVisible({timeout:20_000});
  await page.getByRole('link',{name:'Progress',exact:true}).click();
  await expect(page.getByRole('columnheader',{name:'Mastery estimate',exact:true})).toBeVisible();
  await expect(page.getByRole('rowheader',{name:'Linear equations',exact:true})).toBeVisible();
});
