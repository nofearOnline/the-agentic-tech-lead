/** @type {import('jest').Config} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['<rootDir>/tests/**/*.test.ts'],
  collectCoverageFrom: ['src/**/*.ts'],
  moduleFileExtensions: ['ts', 'js', 'json'],
  clearMocks: true,
  watchman: false,
};
