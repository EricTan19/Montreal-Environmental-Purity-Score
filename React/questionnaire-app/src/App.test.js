jest.mock('./api', () => ({
  API_BASE_URL: 'http://localhost:8000',
  approveComputerSession: jest.fn(),
  continueComputerSession: jest.fn(),
  fetchComputerSession: jest.fn(),
  startComputerSession: jest.fn(),
  submitAnswers: jest.fn(),
}));

import { render, screen } from '@testing-library/react';
import App from './App';

test('renders the questionnaire and computer use panels', () => {
  render(<App />);

  expect(
    screen.getByRole('heading', { name: /repair the app and inspect it with openai computer use/i })
  ).toBeInTheDocument();
  expect(
    screen.getByRole('heading', { name: /environmental purity survey/i })
  ).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: /local inspector/i })).toBeInTheDocument();
});
