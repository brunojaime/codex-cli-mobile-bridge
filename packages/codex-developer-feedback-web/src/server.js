import {bridgeUrl} from './core.js';

/** Server authorization hook for product-owned sessions; no Bridge/product tokens. */
export function createFeedbackConfigHandler(config, authenticate) {
  return async request => {
    if (new URL(request.url).pathname !== '/api/developer-feedback/config') return null;
    const headers={'Cache-Control':'no-store'};
    if (request.method !== 'GET' || config.environment !== 'dev' || !config.allowedOrigins.includes(new URL(request.url).origin)) return new Response(null,{status:404,headers});
    let actor;
    try { actor=await authenticate(request); } catch { return new Response(null,{status:401,headers}); }
    if (!actor || !config.roles.includes(actor.role) || !(actor.userId || actor.user_id)) return new Response(null,{status:403,headers});
    return Response.json({enabled:true,sourceApp:config.sourceApp,sourceDisplayName:config.sourceDisplayName,environment:'dev',allowedOrigins:config.allowedOrigins,bridgeUrl:bridgeUrl(config.bridgeUrl),queueScope:String(actor.userId||actor.user_id)},{headers});
  };
}
