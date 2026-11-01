import type { MermaidConfig } from 'mermaid';

/** Concrete SVG colors keep standalone downloads identical to the app. */
export function mermaidTheme(styles: CSSStyleDeclaration, dark: boolean): Pick<MermaidConfig, 'theme' | 'look' | 'themeVariables' | 'themeCSS'> {
  const color = (name: string) => '#' + styles.getPropertyValue(`--${name}`).trim().split(/\s+/).slice(0, 3)
    .map(value => Math.round(Number(value)).toString(16).padStart(2, '0')).join('');
  const font = "'Inter Variable', Inter, 'Noto Naskh Arabic Variable', system-ui, sans-serif";
  const card = color('card'), surface = color('surface'), border = color('border-strong');
  const text = color('foreground'), muted = color('muted'), accent = color('accent');
  return {
    theme: 'base', look: 'classic',
    themeVariables: {
      darkMode: dark, background: color('background'), fontFamily: font, fontSize: '14px',
      primaryColor: card, primaryTextColor: text, primaryBorderColor: border,
      secondaryColor: color('active'), secondaryTextColor: text, secondaryBorderColor: border,
      tertiaryColor: surface, tertiaryTextColor: text, tertiaryBorderColor: color('border'),
      mainBkg: card, nodeBorder: border, nodeTextColor: text, textColor: text,
      lineColor: muted, defaultLinkColor: muted, edgeLabelBackground: card,
      clusterBkg: surface, clusterBorder: color('border'), titleColor: text,
      actorBkg: card, actorBorder: border, actorTextColor: text, actorLineColor: muted,
      signalColor: muted, signalTextColor: text, labelBoxBkgColor: card,
      labelBoxBorderColor: border, labelTextColor: text, loopTextColor: text,
      noteBkgColor: color('active'), noteBorderColor: border, noteTextColor: text,
      activationBkgColor: surface, activationBorderColor: border,
      pie1: accent, pie2: color('success'), pie3: color('warning'), pie4: color('danger'),
      pie5: color('border-strong'), pie6: color('muted'), pieTitleTextColor: text,
      pieSectionTextColor: text, pieLegendTextColor: text, pieStrokeColor: card,
    },
    themeCSS: `
      text { font-family: ${font}; font-weight: 450; }
      .node rect, .cluster rect, rect.actor, rect.labelBox { rx: 10px; ry: 10px; }
      .node, .node rect, .node polygon, .node path, .cluster rect { filter: none !important; }
      .node rect, .node polygon, .node path, .cluster rect { stroke-width: 1px; }
      .flowchart-link { stroke-width: 1.35px; }
      .cluster-label text, .actor text, .titleText { font-weight: 600; }
    `,
  };
}
