import { expect, type Locator } from '@playwright/test';

export async function chooseOption(control: Locator, value: string) {
  control = control.and(control.page().getByRole('combobox'));
  await control.click();
  await expect(control).toHaveAttribute('aria-expanded', 'true');
  const listId = await control.getAttribute('aria-controls');
  await control.page().locator(`[id=${JSON.stringify(listId)}] [role="option"][data-value=${JSON.stringify(value)}]`).click();
}
