import axios from 'axios';

export const API_BASE_URL = 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
});

export async function submitAnswers(answers) {
  const response = await api.post('/submit_answers', { answers });
  return response.data;
}

export async function startComputerSession(payload) {
  const response = await api.post('/computer-use/sessions', payload);
  return response.data;
}

export async function fetchComputerSession(sessionId) {
  const response = await api.get(`/computer-use/sessions/${sessionId}`);
  return response.data;
}

export async function continueComputerSession(sessionId) {
  const response = await api.post(`/computer-use/sessions/${sessionId}/continue`);
  return response.data;
}

export async function approveComputerSession(sessionId, approved) {
  const response = await api.post(`/computer-use/sessions/${sessionId}/approval`, {
    approved,
  });
  return response.data;
}

export default api;
