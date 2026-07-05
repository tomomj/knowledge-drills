/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: 'no-circular',
      severity: 'error',
      from: {},
      to: { circular: true },
    },
    {
      name: 'no-components-to-api',
      severity: 'error',
      from: { path: '^src/components' },
      to: { path: '^src/api' },
    },
    {
      name: 'no-lib-to-react',
      severity: 'error',
      from: { path: '^src/lib' },
      to: { dependencyTypes: ['npm'], path: '^react' },
    },
    {
      name: 'no-api-to-pages-or-components',
      severity: 'error',
      from: { path: '^src/api' },
      to: { path: '^src/(pages|components)' },
    },
  ],
  options: {
    doNotFollow: { path: 'node_modules' },
    tsPreCompilationDeps: true,
    enhancedResolveOptions: {
      conditionNames: ['import', 'require', 'node', 'default'],
      exportsFields: ['exports'],
    },
  },
}
