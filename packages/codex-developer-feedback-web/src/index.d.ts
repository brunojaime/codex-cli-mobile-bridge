export interface FeedbackConfig {
  sourceApp: string;
  sourceDisplayName: string;
  environment: 'dev' | 'qa' | 'staging';
  allowedOrigins: string[];
  bridgeUrl: string;
  workspacePath?: string;
  queueScope?: string;
  launcherLabel?: string;
  position?: 'top-right' | 'bottom-right';
  offset?: number;
  compactBottomOffset?: number;
  suspendWhen?: string[];
  randomUUID?: () => string;
  sha256?: (content: string) => Promise<string>;
}
export function mountFeedback(config: FeedbackConfig): () => void;
