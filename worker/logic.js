const CACHE = new Map();
async function retrieve(args = {}) {
  const days = args.days ?? 7, mag = args.min_magnitude ?? 2.5, depth = args.max_depth ?? 1000, place = args.place ?? '';
  if (![1,7,30].includes(days)) throw Error('days must be 1, 7 or 30');
  if (typeof mag !== 'number' || !Number.isFinite(mag) || mag < 2.5 || mag > 10) throw Error('min_magnitude must be between 2.5 and 10');
  if (typeof depth !== 'number' || !Number.isFinite(depth) || depth < -10 || depth > 1000) throw Error('max_depth must be between -10 and 1000');
  if (typeof place !== 'string' || place.length > 100) throw Error('place must be a string of at most 100 characters');
  const sourceUrl = `https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_${({1:'day',7:'week',30:'month'})[days]}.geojson`;
  let cached = CACHE.get(days);
  if (!cached || Date.now() - cached.ts > 60000) {
    const response = await fetch(sourceUrl, {signal: AbortSignal.timeout(25000)});
    if (!response.ok) throw Error(`USGS returned HTTP ${response.status}`);
    cached = {data: await response.json(), fetchedAt: new Date().toISOString(), ts: Date.now()};
    CACHE.set(days, cached);
  }
  const events = cached.data.features.filter(f => f.properties.type === 'earthquake' && f.properties.mag != null).map(f => {
    const p = f.properties, c = f.geometry.coordinates;
    return {id:f.id,magnitude:p.mag,place:p.place||'Location not reported',time:p.time,updated:p.updated,longitude:c[0],latitude:c[1],depth:c[2],url:p.url,status:p.status,magType:p.magType,felt:p.felt};
  }).sort((a,b)=>b.time-a.time);
  const count=events.filter(e=>e.magnitude>=mag&&e.depth<=depth&&e.place.toLowerCase().includes(place.toLowerCase())).length;
  return {events,count,catalogCount:events.length,source:'USGS Earthquake Hazards Program',sourceUrl,fetchedAt:cached.fetchedAt,feedGenerated:cached.data.metadata.generated,filters:{days,min_magnitude:mag,max_depth:depth,place},note:'Catalog includes M2.5+ earthquakes. Count matches filters; events contains the whole time-range catalog so widget filters can be widened. Preliminary events may be revised. Place matches USGS descriptions. No predictions.'};
}
async function rpc(body) {
  const {method,id,params={}}=body;
  if (id===undefined) return null;
  let result={};
  if (method==='initialize') result={protocolVersion:'2025-06-18',capabilities:{tools:{},resources:{}},serverInfo:{name:'seismic-usgs-explorer',version:'1.0.0'}};
  else if(method==='server/discover') result={supportedVersions:['2026-07-28','2025-06-18'],capabilities:{tools:{},resources:{}}};
  else if(method==='ping') result={};
  else if(method==='tools/list') result={tools:[TOOL]};
  else if(method==='resources/list') result={resources:[{uri:RESOURCE,name:'Seismic explorer',mimeType:'text/html+skybridge'}]};
  else if(method==='resources/templates/list') result={resourceTemplates:[]};
  else if(method==='resources/read') {
    if(params.uri!==RESOURCE) return {jsonrpc:'2.0',id,error:{code:-32602,message:'Unknown resource URI'}};
    result={contents:[{uri:RESOURCE,mimeType:'text/html+skybridge',text:HTML,_meta:{'openai/widgetDescription':'Interactive USGS earthquake map and explorer with magnitude, depth, place and time filters.','openai/widgetPrefersBorder':true,'openai/widgetCSP':{connect_domains:[],resource_domains:[]}}}]};
  } else if(method==='tools/call') {
    try {
      if(params.name!==TOOL.name)throw Error('Unknown tool');
      const data=await retrieve(params.arguments||{});
      result={content:[{type:'text',text:`Retrieved ${data.count} matching earthquakes from USGS for the last ${data.filters.days} days. Use the embedded explorer to filter and inspect. Source: ${data.sourceUrl}. Fetched: ${data.fetchedAt}.`}],structuredContent:data,_meta:{'openai/outputTemplate':RESOURCE}};
    } catch(error) {result={isError:true,content:[{type:'text',text:'USGS retrieval failed: '+error.message}]};}
  } else return {jsonrpc:'2.0',id,error:{code:-32601,message:'Method not found'}};
  return {jsonrpc:'2.0',id,result};
}
const headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Content-Type, Accept, MCP-Protocol-Version, Mcp-Session-Id','Access-Control-Allow-Methods':'POST, GET, OPTIONS'};
const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{...headers,'Content-Type':'application/json'}});
export default {async fetch(request) {
  const url=new URL(request.url);
  if(request.method==='OPTIONS')return new Response(null,{status:204,headers});
  if(url.pathname==='/health')return json({status:'ok',service:'seismic-usgs-mcp'});
  if(url.pathname==='/'||url.pathname==='/widget')return new Response(HTML,{headers:{...headers,'Content-Type':'text/html; charset=utf-8'}});
  if(url.pathname==='/api/earthquakes') {try{return json(await retrieve({days:Number(url.searchParams.get('days')||7)}));}catch(e){return json({error:e.message},502);}}
  if(['/mcp','/api/mcp'].includes(url.pathname.replace(/\/$/,''))) {
    if(request.method!=='POST')return json({error:'Use POST for stateless MCP requests'},405);
    try{const body=await request.json();const response=await rpc(body);return response===null?new Response(null,{status:202,headers}):json(response);}catch{return json({jsonrpc:'2.0',id:null,error:{code:-32700,message:'Invalid JSON-RPC request'}},400);}
  }
  return json({error:'Not found'},404);
}};

