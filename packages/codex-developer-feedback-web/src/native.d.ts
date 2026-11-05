import type {FeedbackConfig} from './index.js';
export interface FeedbackStorage {getItem(key:string):Promise<string|null>;setItem(key:string,value:string):Promise<void>}
export interface NativeFeedbackItem {id:string;sourceApp:string;comment:string;screenshotPngBase64:string;[key:string]:unknown}
export interface NativeFeedbackClient {
 key:string; pending():Promise<NativeFeedbackItem[]>;
 legacyUncertain():Promise<boolean>;
 reconcileLegacy(resolution:'received'|'not-received'):Promise<void>;
 capture(input:{screenshot:string;comment?:string;width:number;height:number;pathname?:string;points?:{x:number;y:number}[];audio?:{base64:string;mimeType:string;durationMs:number;byteLength:number}}):Promise<NativeFeedbackItem>;
 remove(id:string):Promise<void>;
 presets():Promise<{presets:{id:string;name:string}[];defaultPresetId?:string}>;
 send(preset:string, executionMode?:'execute'|'backlog'):Promise<Record<string,unknown>>;
}
export function createNativeFeedback(config:Omit<FeedbackConfig,'allowedOrigins'> & {queueScope:string;legacyQueueKeys?:string[];legacyUncertainKeys?:string[]},storage:FeedbackStorage,fetcher?:typeof fetch):NativeFeedbackClient;
