import globals from 'globals';

export default [{
  files: ['web/**/*.js'],
  languageOptions: {ecmaVersion: 2022, sourceType: 'script', globals: globals.browser},
  rules: {
    'no-unused-vars': ['error', {args: 'after-used', ignoreRestSiblings: true}],
    'no-undef': 'error',
    'no-unreachable': 'error',
    'no-dupe-args': 'error',
    'no-dupe-keys': 'error',
    'no-constant-condition': 'error',
    'no-unsafe-finally': 'error',
    'valid-typeof': 'error'
  }
}];
