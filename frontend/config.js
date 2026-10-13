// Single source of truth for the backend URL. Every page/module imports
// this instead of hardcoding its own copy (the old project had the upload
// page pointing at the wrong port because it didn't do this).
const config = {
  API_BASE_URL: window.location.origin,
};

export default config;
