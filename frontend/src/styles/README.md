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
Interactive color transitions are scoped to controls; initial theme selection does
not animate. Avoid universal transition selectors. Reduced motion and forced colors
retain static status and visible focus.

Compact geometry uses `rounded-control` (9px), `rounded-panel` (14px), 32/36/40px
button sizes and 36px fields. Coarse pointers get larger hit areas without oversized
glyphs. Shared workspace classes define headers, 16px panels, filters, tabs,
statuses and action rows. Ordinary panels have no blur or large shadow.
`shadow-panel` provides optional lift; `shadow-overlay` is reserved for overlays.

Hover/focus lasts 100–150ms; overlays enter in 130–160ms. New completed answers
reveal as one rendered Markdown surface with a feathered downward mask over 900ms.
History and reduced-motion answers appear immediately. Reserve the final layout
and avoid animated dimensions. The working logo stays instance-scoped.

Run `npm run check:theme` for theme behavior checks and `npm run build` for
TypeScript validation and the production bundle. The behavior checks use a
simulated browser environment; visual review still requires a browser.
`npm run test:auth` includes real browser checks of both palettes and responsive auth
pages, with screenshots in `test-results/`. See `docs/frontend-auth.md` at the repository
root for the PostgreSQL test setup.

`npm run check:ui` checks semantic text palettes, input boundaries, primary action
contrast and explicit-transition policy. Browser screenshots and keyboard checks
supplement these rules. Hashed production assets use immutable cache headers and
gzip; HTML and `theme.js` revalidate so releases load correctly.
