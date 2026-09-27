export interface FeedbackConfig {
  sourceApp: string;
  sourceDisplayName: string;
  environment: 'dev' | 'qa' | 'staging';
  allowedOrigins: string[];
  bridgeUrl: string;
}
export function mountFeedback(config: FeedbackConfig): () => void;
