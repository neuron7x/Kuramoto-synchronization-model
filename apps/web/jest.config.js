const nextJest = require('next/jest')

const createJestConfig = nextJest({ dir: './' })

const customJestConfig = {
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
  testEnvironment: 'jest-environment-jsdom',
  moduleNameMapper: {
    '^.+\\.(css|less|scss|sass)$': 'identity-obj-proxy',
  },
  testPathIgnorePatterns: ['<rootDir>/tests/'],
  collectCoverageFrom: [
    '<rootDir>/app/**/*.{ts,tsx}',
    '!<rootDir>/**/types/**',
    '!<rootDir>/**/node_modules/**',
  ],
}

module.exports = createJestConfig(customJestConfig)
