Use semantic Tailwind colors for every component. Both palettes live in
`global.css`; their Tailwind names are registered in `tailwind.config.js`.

- Backgrounds: `bg-background`, `bg-card`, `bg-surface`, `bg-input`.
- Text: `text-foreground`, `text-heading`, `text-body`, `text-muted`, `text-subtle`.
- Borders: `border-border`, `border-border-strong`, `border-border-hover`.
- Interaction: `bg-hover`, `bg-active`, `ring-accent`, `border-accent`.
- Primary actions: `bg-primary text-accent-foreground hover:bg-primary-hover`.
- Feedback and chat: `text-danger`, `bg-message`.

Opacity modifiers work normally, such as `ring-accent/40`. CSS outside Tailwind
can use `rgb(var(--heading))`. Add new semantic roles centrally when needed;
avoid palette utilities, literal colors, and component-level theme branches.

`public/theme.js` selects the initial palette before React loads.
`ThemeProvider` owns preference persistence, OS updates, and tab synchronization.
New users default to System. Only the appearance selector needs `useTheme`.
Theme transitions honor reduced motion and start after the initial paint.

Run `npm run check:theme` for theme behavior checks and `npm run build` for
TypeScript validation and the production bundle. The behavior checks use a
simulated browser environment; visual review still requires a browser.
`npm run test:auth` includes real browser checks of both palettes and responsive auth
pages, with screenshots in `test-results/`. See `docs/frontend-auth.md` at the repository
root for the PostgreSQL test setup.
