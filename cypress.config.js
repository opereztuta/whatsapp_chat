module.exports = {
  defaultCommandTimeout: 20000,
  pageLoadTimeout: 30000,
  video: false,
  viewportHeight: 960,
  viewportWidth: 1400,
  e2e: {
    baseUrl: process.env.CYPRESS_BASE_URL || "http://host.docker.internal:8001",
    specPattern: "cypress/integration/*.js",
    supportFile: "cypress/support/e2e.js",
  },
};
