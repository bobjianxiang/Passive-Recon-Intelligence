import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
});

export const getJobSummary = async (jobId, generateIfMissing = true) => {
  const response = await api.get(`/api/v1/jobs/${jobId}/summary`, {
    params: { generate_if_missing: generateIfMissing },
  });
  return response.data;
};

export const getJobGraph = async (jobId) => {
  const response = await api.get(`/api/v1/jobs/${jobId}/export/graph`);
  return response.data;
};

export const createReconJob = async (targetDomain) => {
  const response = await api.post('/api/v1/jobs', { target_domain: targetDomain });
  return response.data;
};