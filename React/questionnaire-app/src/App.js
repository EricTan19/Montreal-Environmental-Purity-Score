import React, { useState } from 'react';
import './App.css';
import {
  API_BASE_URL,
  approveComputerSession,
  continueComputerSession,
  fetchComputerSession,
  startComputerSession,
  submitAnswers,
} from './api';

const transportOptions = [
  'Combustion Engine Vehicle',
  'Electric Powered Car',
  'Public Transport',
  'Bicycle',
];

const flightOptions = ['0', '1', '2', '3', '4 or more'];
const compostOptions = ['Yes', 'No'];
const dietOptions = ['Vegan', 'Vegetarian', 'Other diet'];

const initialAnswers = {
  transportMode: 'Public Transport',
  transportFrequency: '0.5',
  flights: '0',
  compost: 'Yes',
  recycleFrequency: '0.5',
  diet: 'Vegetarian',
};

const initialComputerForm = {
  url: 'http://127.0.0.1:3000',
  task: 'Open the local Montreal Environmental Purity Score app, complete the questionnaire with representative answers, and identify the most obvious UI, copy, or flow defects. Stay on localhost and stop when approval is required.',
  model: 'computer-use-preview',
  display_width: 1280,
  display_height: 900,
  max_steps_per_run: 8,
  headless: true,
  allowed_hosts: ['127.0.0.1', 'localhost'],
};

function toImageUrl(path) {
  if (!path) {
    return '';
  }

  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }

  return `${API_BASE_URL}${path}`;
}

function formatPercent(value) {
  return `${Math.round(Number(value) * 100)}%`;
}

function getErrorMessage(error) {
  return (
    error?.response?.data?.detail ||
    error?.message ||
    'Something went wrong while talking to the backend.'
  );
}

function StatusBadge({ status }) {
  return <span className={`status-badge status-${status || 'idle'}`}>{status || 'idle'}</span>;
}

function App() {
  const [answers, setAnswers] = useState(initialAnswers);
  const [result, setResult] = useState(null);
  const [questionnaireBusy, setQuestionnaireBusy] = useState(false);
  const [questionnaireError, setQuestionnaireError] = useState('');

  const [computerForm, setComputerForm] = useState(initialComputerForm);
  const [computerSession, setComputerSession] = useState(null);
  const [computerBusy, setComputerBusy] = useState(false);
  const [computerError, setComputerError] = useState('');

  const serializedAnswers = [
    `${answers.transportMode}, ${answers.transportFrequency}`,
    answers.flights,
    answers.compost,
    answers.recycleFrequency,
    answers.diet,
  ];

  const updateAnswer = (field) => (event) => {
    setAnswers((current) => ({
      ...current,
      [field]: event.target.value,
    }));
  };

  const updateComputerForm = (field) => (event) => {
    const value =
      field === 'display_width' ||
      field === 'display_height' ||
      field === 'max_steps_per_run'
        ? Number(event.target.value)
        : event.target.value;

    setComputerForm((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const runComputerRequest = async (request) => {
    setComputerBusy(true);
    setComputerError('');

    try {
      const nextSession = await request;
      setComputerSession(nextSession);
    } catch (error) {
      setComputerError(getErrorMessage(error));
    } finally {
      setComputerBusy(false);
    }
  };

  const handleQuestionnaireSubmit = async (event) => {
    event.preventDefault();
    setQuestionnaireBusy(true);
    setQuestionnaireError('');

    try {
      const nextResult = await submitAnswers(serializedAnswers);
      setResult(nextResult);
    } catch (error) {
      setQuestionnaireError(getErrorMessage(error));
    } finally {
      setQuestionnaireBusy(false);
    }
  };

  const handleComputerStart = async (event) => {
    event.preventDefault();
    setComputerSession(null);
    await runComputerRequest(startComputerSession(computerForm));
  };

  const handleComputerRefresh = async () => {
    if (!computerSession) {
      return;
    }
    await runComputerRequest(fetchComputerSession(computerSession.id));
  };

  const handleComputerContinue = async () => {
    if (!computerSession) {
      return;
    }
    await runComputerRequest(continueComputerSession(computerSession.id));
  };

  const handleComputerApproval = async (approved) => {
    if (!computerSession) {
      return;
    }
    await runComputerRequest(approveComputerSession(computerSession.id, approved));
  };

  return (
    <div className="page-shell">
      <header className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Montreal Environmental Purity Score</p>
          <h1>Repair the app and inspect it with OpenAI Computer Use.</h1>
          <p className="hero-body">
            The questionnaire now uses a structured FastAPI response, and the side panel can
            launch a Computer Use session against the local frontend with explicit approval gates.
          </p>
        </div>
        <div className="hero-mark">
          <img src="/realLogo.png" alt="MEPS logo" />
        </div>
      </header>

      <main className="workspace">
        <section className="panel questionnaire-panel">
          <div className="panel-header">
            <div>
              <p className="panel-label">Questionnaire</p>
              <h2>Environmental purity survey</h2>
            </div>
            <img src="/logo.png" alt="Eco hero mascot" className="panel-art" />
          </div>

          <form onSubmit={handleQuestionnaireSubmit} className="questionnaire-form">
            <article className="question-card">
              <h3>1. What&apos;s your preferred method of transportation?</h3>
              <div className="option-grid">
                {transportOptions.map((option) => (
                  <label key={option} className="option-tile">
                    <input
                      type="radio"
                      name="transportMode"
                      value={option}
                      checked={answers.transportMode === option}
                      onChange={updateAnswer('transportMode')}
                    />
                    <span>{option}</span>
                  </label>
                ))}
              </div>
              <div className="slider-field">
                <div className="slider-copy">
                  <span>How often do you use it?</span>
                  <strong>{formatPercent(answers.transportFrequency)}</strong>
                </div>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={answers.transportFrequency}
                  onChange={updateAnswer('transportFrequency')}
                />
              </div>
            </article>

            <article className="question-card">
              <h3>2. How many times do you travel by airplane per year?</h3>
              <div className="option-grid compact-grid">
                {flightOptions.map((option) => (
                  <label key={option} className="option-tile">
                    <input
                      type="radio"
                      name="flights"
                      value={option}
                      checked={answers.flights === option}
                      onChange={updateAnswer('flights')}
                    />
                    <span>{option}</span>
                  </label>
                ))}
              </div>
            </article>

            <article className="question-card">
              <h3>3. Do you compost?</h3>
              <div className="option-grid compact-grid">
                {compostOptions.map((option) => (
                  <label key={option} className="option-tile">
                    <input
                      type="radio"
                      name="compost"
                      value={option}
                      checked={answers.compost === option}
                      onChange={updateAnswer('compost')}
                    />
                    <span>{option}</span>
                  </label>
                ))}
              </div>
            </article>

            <article className="question-card">
              <h3>4. How often do you recycle?</h3>
              <div className="slider-field">
                <div className="slider-copy">
                  <span>Recycling frequency</span>
                  <strong>{formatPercent(answers.recycleFrequency)}</strong>
                </div>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={answers.recycleFrequency}
                  onChange={updateAnswer('recycleFrequency')}
                />
              </div>
            </article>

            <article className="question-card">
              <h3>5. What is your diet?</h3>
              <div className="option-grid compact-grid">
                {dietOptions.map((option) => (
                  <label key={option} className="option-tile">
                    <input
                      type="radio"
                      name="diet"
                      value={option}
                      checked={answers.diet === option}
                      onChange={updateAnswer('diet')}
                    />
                    <span>{option}</span>
                  </label>
                ))}
              </div>
            </article>

            {questionnaireError ? <p className="error-text">{questionnaireError}</p> : null}

            <button className="primary-button" type="submit" disabled={questionnaireBusy}>
              {questionnaireBusy ? 'Scoring...' : 'Calculate purity score'}
            </button>
          </form>
        </section>

        <section className="panel computer-panel">
          <div className="panel-header panel-header-tight">
            <div>
              <p className="panel-label">Computer Use</p>
              <h2>Local inspector</h2>
            </div>
            <StatusBadge status={computerSession?.status} />
          </div>

          <form onSubmit={handleComputerStart} className="computer-form">
            <label className="field">
              <span>Target URL</span>
              <input
                type="url"
                value={computerForm.url}
                onChange={updateComputerForm('url')}
                placeholder="http://127.0.0.1:3000"
              />
            </label>

            <label className="field">
              <span>Task</span>
              <textarea
                rows="5"
                value={computerForm.task}
                onChange={updateComputerForm('task')}
              />
            </label>

            <div className="inline-fields">
              <label className="field">
                <span>Width</span>
                <input
                  type="number"
                  min="640"
                  max="2560"
                  value={computerForm.display_width}
                  onChange={updateComputerForm('display_width')}
                />
              </label>
              <label className="field">
                <span>Height</span>
                <input
                  type="number"
                  min="480"
                  max="1600"
                  value={computerForm.display_height}
                  onChange={updateComputerForm('display_height')}
                />
              </label>
              <label className="field">
                <span>Step budget</span>
                <input
                  type="number"
                  min="1"
                  max="25"
                  value={computerForm.max_steps_per_run}
                  onChange={updateComputerForm('max_steps_per_run')}
                />
              </label>
            </div>

            {computerError ? <p className="error-text">{computerError}</p> : null}

            <div className="button-row">
              <button className="primary-button" type="submit" disabled={computerBusy}>
                {computerBusy ? 'Launching...' : 'Start session'}
              </button>
              <button
                className="secondary-button"
                type="button"
                onClick={handleComputerContinue}
                disabled={!computerSession || computerBusy}
              >
                Continue
              </button>
              <button
                className="secondary-button"
                type="button"
                onClick={handleComputerRefresh}
                disabled={!computerSession || computerBusy}
              >
                Refresh
              </button>
            </div>
          </form>

          {computerSession ? (
            <div className="session-view">
              <div className="session-meta">
                <p>
                  <strong>Current URL:</strong> {computerSession.current_url || 'Not available yet'}
                </p>
                <p>
                  <strong>Allowed hosts:</strong> {computerSession.allowed_hosts.join(', ')}
                </p>
                <p>
                  <strong>Steps executed:</strong> {computerSession.steps_executed}
                </p>
              </div>

              {computerSession.latest_output_text ? (
                <div className="assistant-note">
                  <p className="panel-label">Assistant output</p>
                  <p>{computerSession.latest_output_text}</p>
                </div>
              ) : null}

              {computerSession.pending_safety_checks?.length ? (
                <div className="approval-box">
                  <p className="panel-label">Approval required</p>
                  {computerSession.pending_safety_checks.map((check) => (
                    <article key={check.id} className="approval-item">
                      <strong>{check.code || 'Safety check'}</strong>
                      <p>{check.message || 'The model requested user approval before continuing.'}</p>
                    </article>
                  ))}
                  <div className="button-row">
                    <button
                      className="primary-button"
                      type="button"
                      onClick={() => handleComputerApproval(true)}
                      disabled={computerBusy}
                    >
                      Approve
                    </button>
                    <button
                      className="danger-button"
                      type="button"
                      onClick={() => handleComputerApproval(false)}
                      disabled={computerBusy}
                    >
                      Deny
                    </button>
                  </div>
                </div>
              ) : null}

              {computerSession.last_error ? (
                <div className="error-panel">
                  <p className="panel-label">Session error</p>
                  <p>{computerSession.last_error}</p>
                </div>
              ) : null}

              {computerSession.screenshot_url ? (
                <div className="screenshot-shell">
                  <img
                    src={toImageUrl(computerSession.screenshot_url)}
                    alt="Latest browser screenshot"
                  />
                </div>
              ) : null}

              <div className="event-feed">
                <p className="panel-label">Recent events</p>
                <ul>
                  {computerSession.event_log.map((entry) => (
                    <li key={`${entry.timestamp}-${entry.kind}`}>
                      <span>{entry.kind}</span>
                      <p>{entry.message}</p>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : null}
        </section>
      </main>

      {result ? (
        <section className="panel results-panel">
          <div className="panel-header panel-header-tight">
            <div>
              <p className="panel-label">Results</p>
              <h2>Your current eco rank</h2>
            </div>
            <div className="score-pill">{result.score}</div>
          </div>

          <div className="results-summary">
            <div className="badge-shell">
              <img src={`/${result.badge_image}`} alt="Eco rank badge" />
            </div>
            <div className="summary-copy">
              <h3>{result.message}</h3>
              <p>
                The score is computed from the questionnaire and returned as structured JSON from
                FastAPI, so the UI no longer relies on parsing a Python string representation.
              </p>
              <code>{JSON.stringify(serializedAnswers)}</code>
            </div>
          </div>

          <div className="graph-grid">
            {result.graphs.map((graphUrl, index) => (
              <figure key={graphUrl} className="graph-card">
                <img src={toImageUrl(graphUrl)} alt={`Question ${index + 1} distribution`} />
                <figcaption>Question {index + 1}</figcaption>
              </figure>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

export default App;
