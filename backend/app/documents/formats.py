MEDIA = {
    'txt': 'text/plain', 'pdf': 'application/pdf',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'png': 'image/png', 'jpg': 'image/jpeg', 'html': 'text/html',
    'py': 'text/x-python', 'js': 'text/javascript', 'ts': 'text/typescript',
    'jsx': 'text/jsx', 'tsx': 'text/tsx', 'java': 'text/x-java-source',
    'c': 'text/x-c', 'cpp': 'text/x-c++', 'cs': 'text/x-csharp',
    'go': 'text/x-go', 'rs': 'text/x-rust', 'rb': 'text/x-ruby',
    'php': 'text/x-php', 'sh': 'text/x-shellscript', 'sql': 'application/sql',
    'json': 'application/json', 'yaml': 'application/yaml', 'toml': 'application/toml',
    'md': 'text/markdown', 'css': 'text/css', 'xml': 'application/xml',
    'ps1': 'text/x-powershell', 'bat': 'text/x-batch', 'kt': 'text/x-kotlin',
    'swift': 'text/x-swift', 'lua': 'text/x-lua', 'r': 'text/x-r-source',
    'vue': 'text/x-vue', 'svelte': 'text/x-svelte', 'scss': 'text/x-scss',
}
# Unique internal media identifiers let the facade recover the language reliably.
MEDIA.update({kind: 'text/x-' + kind for kind in (
    'dart', 'scala', 'clj', 'ex', 'erl', 'hs', 'ml', 'fs', 'vb', 'vbs',
    'pl', 'raku', 'jl', 'groovy', 'm', 'mm', 'zig', 'nim', 'd', 'pas',
    'f90', 'cob', 'asm', 'sol', 'vy', 'v', 'sv', 'vhd', 'cu', 'ino',
    'awk', 'sed', 'fish', 'csh', 'less', 'sass', 'styl', 'graphql', 'proto',
    'hcl', 'dockerfile', 'makefile', 'cmake', 'ini', 'conf', 'env', 'properties',
    'csv', 'tsv', 'rst', 'tex', 'adoc', 'log', 'diff', 'gitignore',
    'gitattributes', 'editorconfig', 'lock', 'ejs', 'hbs', 'mustache', 'jinja',
    'erb', 'razor', 'jsp', 'aspx', 'astro', 'justfile', 'procfile', 'vim',
    'lisp', 'scm', 'rkt', 'tcl', 'cr', 'ada', 'gd', 'glsl', 'hlsl', 'wgsl',
    'metal', 'ninja', 'coffee', 'prisma', 'kql', 'nix', 'cue', 'bicep', 'reg',
)})
CODE_FORMATS = tuple(kind for kind in MEDIA if kind not in ('txt', 'pdf', 'docx', 'pptx', 'png', 'jpg', 'html'))
EXTENSIONS = {'.' + kind: kind for kind in MEDIA}
EXTENSIONS.update({'.jpeg': 'jpg', '.htm': 'html', '.mjs': 'js', '.cjs': 'js', '.mts': 'ts', '.cts': 'ts',
    '.yml': 'yaml', '.h': 'c', '.hpp': 'cpp', '.hh': 'cpp', '.hxx': 'cpp', '.cc': 'cpp', '.cxx': 'cpp',
    '.bash': 'sh', '.zsh': 'sh', '.ksh': 'sh', '.tcsh': 'csh', '.markdown': 'md', '.mdx': 'md',
    '.cmd': 'bat', '.psm1': 'ps1', '.psd1': 'ps1', '.kts': 'kt', '.sc': 'scala',
    '.cljs': 'clj', '.cljc': 'clj', '.edn': 'clj', '.exs': 'ex', '.hrl': 'erl', '.lhs': 'hs',
    '.mli': 'ml', '.fsx': 'fs', '.fsi': 'fs', '.pm': 'pl', '.p6': 'raku', '.rakumod': 'raku',
    '.gradle': 'groovy', '.nims': 'nim', '.pp': 'pas', '.f': 'f90', '.for': 'f90', '.f95': 'f90',
    '.f03': 'f90', '.f08': 'f90', '.cbl': 'cob', '.s': 'asm', '.vhdl': 'vhd', '.vh': 'v',
    '.svh': 'sv', '.cuh': 'cu', '.gql': 'graphql', '.tf': 'hcl', '.tfvars': 'hcl', '.cfg': 'ini',
    '.config': 'conf', '.cnf': 'conf', '.patch': 'diff', '.rest': 'rst', '.ltx': 'tex',
    '.asciidoc': 'adoc', '.j2': 'jinja', '.jinja2': 'jinja', '.cshtml': 'razor',
    '.ipynb': 'json', '.jsonc': 'json', '.jsonl': 'json', '.ndjson': 'json', '.svg': 'xml',
    '.xsd': 'xml', '.xsl': 'xml', '.xslt': 'xml', '.resx': 'xml', '.sln': 'conf',
    '.csproj': 'xml', '.fsproj': 'xml', '.vbproj': 'xml', '.props': 'xml', '.targets': 'xml',
    '.pyi': 'py', '.pyw': 'py', '.phtml': 'php', '.pgsql': 'sql', '.psql': 'sql',
    '.lsp': 'lisp', '.ss': 'scm', '.adb': 'ada', '.ads': 'ada', '.gdshader': 'glsl',
    '.vert': 'glsl', '.frag': 'glsl', '.geom': 'glsl', '.shader': 'hlsl', '.cg': 'hlsl',
    '.cginc': 'hlsl', '.hlsli': 'hlsl', '.bas': 'vb', '.desktop': 'ini', '.service': 'ini'})
FILENAMES = {
    'dockerfile': 'dockerfile', 'containerfile': 'dockerfile',
    'makefile': 'makefile', 'gnumakefile': 'makefile', 'justfile': 'justfile',
    'jenkinsfile': 'groovy', 'vagrantfile': 'rb', 'gemfile': 'rb', 'rakefile': 'rb',
    'procfile': 'procfile', 'cmakelists.txt': 'cmake',
    '.env': 'env', '.gitignore': 'gitignore', '.dockerignore': 'gitignore',
    '.gitattributes': 'gitattributes', '.editorconfig': 'editorconfig', '.gitmodules': 'ini',
    '.npmrc': 'ini', '.yarnrc': 'conf', '.babelrc': 'json', '.eslintrc': 'json', '.prettierrc': 'json',
    '.bashrc': 'sh', '.bash_profile': 'sh', '.zshrc': 'sh', '.profile': 'sh', '.vimrc': 'vim',
    'license': 'md', 'copying': 'md', 'notice': 'md', 'readme': 'md', 'changelog': 'md',
}


def format_for_filename(filename: str) -> str:
    # Accept either client path separator; directory names do not select a reader.
    name = filename.replace('\\', '/').rsplit('/', 1)[-1].lower()
    if name in FILENAMES:
        return FILENAMES[name]
    for prefix, kind in (('dockerfile.', 'dockerfile'), ('containerfile.', 'dockerfile'), ('.env.', 'env')):
        if name.startswith(prefix):
            return kind
    suffix = '.' + name.rsplit('.', 1)[1] if '.' in name else ''
    return EXTENSIONS.get(suffix, '')
