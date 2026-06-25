import { useMutation, useQuery } from '@tanstack/react-query';
import { Bot, ChevronDown, ChevronUp, SearchCheck, Send, Sparkles, User } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { AssistantChatResponse } from '../types';

interface AssistantPanelProps {
  enabled: boolean;
}

interface ChatEntry {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  response?: AssistantChatResponse;
}

const STARTER_PROMPTS = [
  'How was production today?',
  'Compare today to yesterday',
  'How many stops in the last 24 hours?',
  'What changed the most in the last hour?',
  'What changed around the last stop?',
  'What happened in the unwinder today?'
];

const CONVERSATION_STORAGE_KEY = 'bbg_assistant_conversation_id';

function createConversationId() {
  return globalThis.crypto?.randomUUID?.() ?? `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function readConversationId() {
  if (typeof window === 'undefined') return createConversationId();
  const generated = createConversationId();
  try {
    const existing = window.sessionStorage.getItem(CONVERSATION_STORAGE_KEY);
    if (existing) return existing;
    window.sessionStorage.setItem(CONVERSATION_STORAGE_KEY, generated);
  } catch {
    return generated;
  }
  return generated;
}

function AssistantPanel({ enabled }: AssistantPanelProps) {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState<ChatEntry[]>([]);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [showProductionCandidates, setShowProductionCandidates] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [conversationId, setConversationId] = useState(readConversationId);
  const threadRef = useRef<HTMLDivElement | null>(null);

  const chatMutation = useMutation({
    mutationFn: (text: string) => api.assistantChat({ message: text, conversation_id: conversationId }),
    onSuccess: (response, text) => {
      setMessages((prev) => [
        ...prev,
        { id: `user-${prev.length}-${Date.now()}`, role: 'user', text },
        { id: `assistant-${prev.length}-${Date.now()}`, role: 'assistant', text: response.answer, response }
      ]);
      setMessage('');
    }
  });

  const diagnosticsQuery = useQuery({
    queryKey: ['assistant-diagnostics'],
    queryFn: api.getAssistantDiagnostics,
    enabled: expanded && showDiagnostics,
    staleTime: 60_000
  });

  const versionQuery = useQuery({
    queryKey: ['assistant-version'],
    queryFn: api.getAssistantVersion,
    enabled: expanded && showDiagnostics,
    staleTime: 60_000
  });

  const productionCandidatesQuery = useQuery({
    queryKey: ['assistant-production-candidates'],
    queryFn: () => api.getAssistantProductionCandidates('today', 12),
    enabled: expanded && showProductionCandidates,
    staleTime: 60_000
  });

  const submitMessage = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || chatMutation.isPending) return;
    chatMutation.mutate(trimmed);
  };

  const startNewConversation = () => {
    const previousConversationId = conversationId;
    void api.clearAssistantConversation(previousConversationId).catch(() => undefined);
    const nextConversationId = createConversationId();
    if (typeof window !== 'undefined') {
      try {
        window.sessionStorage.setItem(CONVERSATION_STORAGE_KEY, nextConversationId);
      } catch {
        // Keep the in-memory ID if browser storage is unavailable.
      }
    }
    setMessages([]);
    setMessage('');
    setConversationId(nextConversationId);
  };

  useEffect(() => {
    if (!expanded || !threadRef.current) return;
    threadRef.current.scrollTop = threadRef.current.scrollHeight;
  }, [expanded, messages, chatMutation.isPending]);

  return (
    <section className={expanded ? 'assistant-panel panel-fill expanded' : 'assistant-panel panel-fill collapsed'}>
      <div className="panel-title-row assistant-header">
        <div>
          <h2>Process Assistant</h2>
          <p>Read-only production and process analysis from OPC history.</p>
        </div>
        <div className="assistant-header-actions">
          <div className="assistant-status">
            <Sparkles size={16} />
            <span>{enabled ? 'LLM enabled when configured' : 'Deterministic mode available'}</span>
          </div>
          <button className="secondary-button small-button" onClick={() => setExpanded((prev) => !prev)} aria-expanded={expanded}>
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            {expanded ? 'Collapse' : 'Expand'}
          </button>
        </div>
      </div>

      {!expanded && (
        <div className="assistant-collapsed-note">
          Expand to ask questions, check setup diagnostics, and review production or stop analysis.
        </div>
      )}

      {expanded && (
        <>
          <div className="assistant-operator-row">
            <button className="primary-button assistant-new-conversation-button" onClick={startNewConversation}>
              New Conversation
            </button>
            <div className="assistant-control-hint">
              Clear Chat only clears visible messages. New Conversation resets follow-up context.
            </div>
          </div>

          <div className="assistant-toolbar">
            <button className="secondary-button small-button" onClick={() => setShowDiagnostics((prev) => !prev)}>
              <SearchCheck size={14} /> {showDiagnostics ? 'Hide Diagnostics' : 'Check Setup'}
            </button>
            <button className="secondary-button small-button" onClick={() => setShowProductionCandidates((prev) => !prev)}>
              {showProductionCandidates ? 'Hide Production Candidates' : 'Production Candidates'}
            </button>
          </div>

          {showDiagnostics && (
            <div className="assistant-diagnostics">
              {diagnosticsQuery.isLoading && <div className="assistant-empty">Loading diagnostics...</div>}
              {diagnosticsQuery.isError && <div className="error-banner">{(diagnosticsQuery.error as Error).message}</div>}
              {diagnosticsQuery.data && (
                <>
                  <div className="assistant-diagnostics-grid">
                    <div className="assistant-metric-card">
                      <span>Assistant Enabled</span>
                      <strong>{diagnosticsQuery.data.assistant_enabled ? 'Yes' : 'No'}</strong>
                    </div>
                    <div className="assistant-metric-card">
                      <span>OpenAI Configured</span>
                      <strong>{diagnosticsQuery.data.openai_configured ? 'Yes' : 'No'}</strong>
                    </div>
                    <div className="assistant-metric-card">
                      <span>Speed Tag</span>
                      <strong>{diagnosticsQuery.data.required_tags.speed.found ? 'Found' : 'Missing'}</strong>
                    </div>
                    <div className="assistant-metric-card">
                      <span>Good Bag Tag</span>
                      <strong>{diagnosticsQuery.data.required_tags.good_bags.found ? 'Found' : 'Missing'}</strong>
                    </div>
                    <div className="assistant-metric-card">
                      <span>Bad Bag Tag</span>
                      <strong>{diagnosticsQuery.data.required_tags.bad_bags.found ? 'Found' : 'Missing'}</strong>
                    </div>
                    <div className="assistant-metric-card">
                      <span>Latest History</span>
                      <strong>{diagnosticsQuery.data.database.latest_history_timestamp ?? '--'}</strong>
                    </div>
                    <div className="assistant-metric-card">
                      <span>Backend Version</span>
                      <strong>{versionQuery.data?.git_commit?.slice(0, 8) ?? diagnosticsQuery.data.version?.git_commit?.slice(0, 8) ?? '--'}</strong>
                    </div>
                    <div className="assistant-metric-card">
                      <span>Memory</span>
                      <strong>
                        {versionQuery.data?.conversation_memory
                          ? `${versionQuery.data.conversation_memory.conversation_count}/${versionQuery.data.conversation_memory.max_conversations}`
                          : diagnosticsQuery.data.version?.conversation_memory
                            ? `${diagnosticsQuery.data.version.conversation_memory.conversation_count}/${diagnosticsQuery.data.version.conversation_memory.max_conversations}`
                            : '--'}
                      </strong>
                    </div>
                  </div>

                  {!!diagnosticsQuery.data.suggested_fixes.length && (
                    <div className="assistant-diagnostics-block">
                      <h3>Suggested Fixes</h3>
                      <ul className="assistant-fix-list">
                        {diagnosticsQuery.data.suggested_fixes.map((fix) => (
                          <li key={fix}>{fix}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {(['speed', 'good_bags', 'bad_bags'] as const).map((key) => {
                    const item = diagnosticsQuery.data.required_tags[key];
                    if (item.found || !item.suggestions?.length) return null;
                    return (
                      <div className="assistant-diagnostics-block" key={key}>
                        <h3>{key.replace('_', ' ')} suggestions</h3>
                        <div className="table-scroll">
                          <table className="data-table assistant-table">
                            <thead>
                              <tr>
                                <th>Tag ID</th>
                                <th>Label</th>
                                <th>OPC Path</th>
                              </tr>
                            </thead>
                            <tbody>
                              {item.suggestions.map((suggestion) => (
                                <tr key={`${key}-${suggestion.tag_id}`}>
                                  <td>{suggestion.tag_id}</td>
                                  <td>{suggestion.label}</td>
                                  <td>{suggestion.opc_path}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    );
                  })}
                </>
              )}
            </div>
          )}

          {showProductionCandidates && (
            <div className="assistant-diagnostics">
              {productionCandidatesQuery.isLoading && <div className="assistant-empty">Loading production candidates...</div>}
              {productionCandidatesQuery.isError && <div className="error-banner">{(productionCandidatesQuery.error as Error).message}</div>}
              {productionCandidatesQuery.data && (
                <div className="assistant-diagnostics-block">
                  <h3>Production Candidates</h3>
                  <div className="table-scroll">
                    <table className="data-table assistant-table">
                      <thead>
                        <tr>
                          <th>Label</th>
                          <th>Section</th>
                          <th>Delta</th>
                          <th>Raw Delta</th>
                          <th>First</th>
                          <th>Last</th>
                          <th>OPC Path</th>
                        </tr>
                      </thead>
                      <tbody>
                        {productionCandidatesQuery.data.candidates.map((candidate) => (
                          <tr key={`production-candidate-${candidate.tag_id}`}>
                            <td>{candidate.label}</td>
                            <td>{candidate.section_key ?? '--'}</td>
                            <td>{candidate.delta_sum}</td>
                            <td>{candidate.raw_delta}</td>
                            <td>{candidate.first_value ?? '--'}</td>
                            <td>{candidate.last_value ?? '--'}</td>
                            <td>{candidate.opc_path}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="assistant-starters">
            {STARTER_PROMPTS.map((prompt) => (
              <button key={prompt} className="assistant-starter" onClick={() => submitMessage(prompt)} disabled={chatMutation.isPending}>
                {prompt}
              </button>
            ))}
          </div>

          <div className="assistant-thread" ref={threadRef}>
            {!messages.length && (
              <div className="assistant-empty">
                Ask about production, stops, last-hour changes, or a section like the unwinder or dancer.
              </div>
            )}

            {messages.map((entry) => (
              <article key={entry.id} className={entry.role === 'user' ? 'assistant-message user' : 'assistant-message assistant'}>
                <div className="assistant-message-icon">{entry.role === 'user' ? <User size={16} /> : <Bot size={16} />}</div>
                <div className="assistant-message-body">
                  <div className="assistant-message-label">{entry.role === 'user' ? 'You' : 'Assistant'}</div>
                  <p>{entry.text}</p>
                  {entry.response && (
                    <>
                      {entry.response.raw.route?.followup && (
                        <div className="assistant-followup-debug">
                          Follow-up context: {entry.response.raw.route.followup.used_context ? 'used' : 'not used'}
                        </div>
                      )}
                      {entry.response.raw.llm && (
                        <div className="assistant-followup-debug">
                          LLM: {entry.response.raw.llm.used ? 'used' : 'fallback'}
                        </div>
                      )}
                      {!!entry.response.cards.length && (
                        <div className="assistant-card-grid">
                          {entry.response.cards.map((card) => (
                            <div className="assistant-metric-card" key={`${entry.id}-${card.label}`}>
                              <span>{card.label}</span>
                              <strong>
                                {card.value}
                                {card.unit ? ` ${card.unit}` : ''}
                              </strong>
                            </div>
                          ))}
                        </div>
                      )}

                      {entry.response.tables.map((table) => {
                        if (table.title === 'Warnings') {
                          return (
                            <details className="assistant-warning-shell" key={`${entry.id}-${table.title}`}>
                              <summary>Warnings</summary>
                              <div className="assistant-warning-list">
                                {table.rows.length ? (
                                  table.rows.map((row, rowIndex) => (
                                    <div className="assistant-warning-item" key={`${entry.id}-${table.title}-${rowIndex}`}>
                                      {row[0] == null ? '--' : String(row[0])}
                                    </div>
                                  ))
                                ) : (
                                  <div className="assistant-warning-item">No warnings.</div>
                                )}
                              </div>
                            </details>
                          );
                        }
                        return (
                          <div className="assistant-table-shell" key={`${entry.id}-${table.title}`}>
                            <h3>{table.title}</h3>
                            <div className="table-scroll">
                              <table className="data-table assistant-table">
                                <thead>
                                  <tr>
                                    {table.columns.map((column) => (
                                      <th key={`${entry.id}-${table.title}-${column}`}>{column}</th>
                                    ))}
                                  </tr>
                                </thead>
                                <tbody>
                                  {table.rows.length ? (
                                    table.rows.map((row, rowIndex) => (
                                      <tr key={`${entry.id}-${table.title}-${rowIndex}`}>
                                        {row.map((cell, cellIndex) => (
                                          <td key={`${entry.id}-${table.title}-${rowIndex}-${cellIndex}`}>{cell == null ? '--' : String(cell)}</td>
                                        ))}
                                      </tr>
                                    ))
                                  ) : (
                                    <tr>
                                      <td colSpan={table.columns.length}>No rows returned.</td>
                                    </tr>
                                  )}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        );
                      })}
                    </>
                  )}
                </div>
              </article>
            ))}

            {chatMutation.isPending && (
              <article className="assistant-message assistant">
                <div className="assistant-message-icon"><Bot size={16} /></div>
                <div className="assistant-message-body">
                  <div className="assistant-message-label">Assistant</div>
                  <p>Analyzing OPC history...</p>
                </div>
              </article>
            )}
          </div>

          {chatMutation.isError && <div className="error-banner">{(chatMutation.error as Error).message}</div>}

          <div className="assistant-compose">
            <textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="Ask about production, stops, sections, or process changes..."
              rows={3}
            />
            <div className="assistant-compose-actions">
              <button
                className="danger-button assistant-clear-button"
                onClick={() => {
                  setMessages([]);
                  setMessage('');
                }}
                disabled={!messages.length && !message.trim()}
              >
                Clear Chat
              </button>
              <button className="primary-button" onClick={() => submitMessage(message)} disabled={chatMutation.isPending || !message.trim()}>
                <Send size={16} /> Send
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

export default AssistantPanel;
