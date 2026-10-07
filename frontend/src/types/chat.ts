export interface ChatMessageData {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

export type ChatTurn = Pick<ChatMessageData, 'role' | 'content'>;

export interface ChatResponse {
  role: 'assistant';
  content: string;
}
