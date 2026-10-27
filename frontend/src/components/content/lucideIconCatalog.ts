import dynamicIconImports from 'lucide-react/dynamicIconImports';

// Only names in the installed package can select a module. Model text never
// becomes an import path, URL, SVG payload or arbitrary React property.
const names = new Map(Object.keys(dynamicIconImports).map(name => [name.replace(/-/g, '').toLowerCase(), name as keyof typeof dynamicIconImports]));
export async function loadIcon(normalizedName: string) {
  const name = names.get(normalizedName);
  return name ? (await dynamicIconImports[name]()).default : undefined;
}
