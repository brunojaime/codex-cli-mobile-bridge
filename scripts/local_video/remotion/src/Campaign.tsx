import React from 'react';
import {AbsoluteFill,Composition,Img,Sequence,interpolate,staticFile,useCurrentFrame} from 'remotion';
import stories from '../campaign.json';

const ink='#1b3038', paper='#f4f6f5';
const clamp={extrapolateLeft:'clamp',extrapolateRight:'clamp'} as const;
const ease=(f:number,d=0)=>1-Math.pow(1-interpolate(f,[d,d+18],[0,1],clamp),4);
type Scene={layout:string;lines:string[];label?:string;seconds:number;light?:boolean;asset?:string;mobile?:string;items?:string[];number?:string};
type Story=typeof stories[number];
const asset=(name:string)=>staticFile('campaign/'+name);
const captureFrame=(name:string,f:number)=>asset(`${name}-frames/${String(Math.min(119,Math.floor(f/2))).padStart(3,'0')}.jpg`);

const Heading:React.FC<{scene:Scene;accent:string}> = ({scene,accent})=>{
  const f=useCurrentFrame();
  const longest=Math.max(...scene.lines.map(s=>s.length));
  const size=Math.min(scene.layout==='type'?94:86,Math.floor(1030/Math.max(longest,12)));
  return <div style={{position:'absolute',left:54,right:48,top:scene.layout==='close'?240:213}}>
    {scene.lines.map((line,i)=><div key={line} style={{overflow:'hidden',paddingBottom:12,marginBottom:-10}}>
      <div style={{fontSize:size,fontWeight:700,lineHeight:1.12,letterSpacing:-3.5,
        color:i===scene.lines.length-1 && !scene.light?accent:undefined,
        transform:`translateY(${(1-ease(f,i*4))*(i===0?10:110)}%)`}}>{line}</div>
    </div>)}
    {scene.label && <div style={{fontSize:24,lineHeight:1.4,marginTop:30,maxWidth:590,opacity:ease(f,10)}}>{scene.label}</div>}
  </div>;
};

const Browser:React.FC<{file:string;top?:number;height?:number;label?:string;rotate?:number}>=({file,top=650,height=380,label='Proyecto real',rotate=0})=>{
  const f=useCurrentFrame();
  return <div style={{position:'absolute',left:40,right:40,top,height,borderRadius:20,overflow:'hidden',background:'#fff',boxShadow:'0 28px 90px #0004',
    transform:`translateY(${(1-ease(f,5))*65}px) rotate(${rotate}deg) scale(${.96+ease(f,5)*.04})`}}>
    <div style={{height:35,display:'flex',gap:7,alignItems:'center',padding:'0 16px',background:'#dbe3e1',color:ink}}>
      {[0,1,2].map(i=><span key={i} style={{width:7,height:7,borderRadius:10,background:'#8ba2aa'}}/>)}
      <span style={{fontSize:12,marginLeft:18}}>{label}</span>
    </div>
    <Img src={asset(file)} style={{width:'100%',height:height-35,objectFit:'cover',objectPosition:'top'}}/>
  </div>;
};

const Network:React.FC<{accent:string}>=({accent})=>{
  const f=useCurrentFrame();
  const nodes=[{x:80,y:40,t:'Tu web'},{x:420,y:40,t:'Gestión'},{x:80,y:295,t:'Equipo'},{x:420,y:295,t:'Datos'}];
  return <div style={{position:'absolute',left:55,top:690,width:610,height:400}}>
    <svg width="610" height="400" style={{position:'absolute'}}>{nodes.map((n,i)=><path key={i} d={`M305 185 L${n.x+55} ${n.y+30}`} stroke={accent} strokeWidth="2" opacity=".6" strokeDasharray="8 8" strokeDashoffset={-f*1.5}/>)}</svg>
    <div style={{position:'absolute',left:243,top:130,width:124,height:108,borderRadius:30,background:accent,color:ink,display:'grid',placeItems:'center',fontSize:40,transform:`scale(${.9+ease(f)*.1})`}}>↔</div>
    {nodes.map((n,i)=><div key={i} style={{position:'absolute',left:n.x-10,top:n.y,width:130,height:68,display:'grid',placeItems:'center',border:'1px solid #7f9ea7',borderRadius:18,fontSize:21,background:ink,opacity:ease(f,i*3)}}>{n.t}</div>)}
  </div>;
};

const CardList:React.FC<{items:string[];accent:string;light?:boolean;stack?:boolean}>=({items,accent,light,stack})=>{
  const f=useCurrentFrame();
  return <div style={{position:'absolute',left:54,right:54,top:650}}>{items.map((item,i)=>{
    const e=ease(f,8+i*5);
    return <div key={item} style={{height:105,marginBottom:18,padding:'0 26px',display:'flex',alignItems:'center',justifyContent:'space-between',borderRadius:18,
      background:light?'#e1e9e6':'#294650',border:`1px solid ${light?'#c1cfca':'#4f6c77'}`,
      fontSize:28,transform:`translateX(${(1-e)*(i%2?-100:100)}px) rotate(${stack?(1-e)*(i%2?-6:6):0}deg)`,opacity:.4+e*.6}}>
      <span>{item}</span><span style={{color:light?ink:accent,fontSize:24}}>↗</span>
    </div>;
  })}</div>;
};

const SceneView:React.FC<{scene:Scene;story:Story;index:number}>=({scene,story,index})=>{
  const f=useCurrentFrame();
  const end=interpolate(f,[scene.seconds*30-8,scene.seconds*30],[0,1],clamp);
  const ocean=scene.layout==='ocean';
  const light=scene.layout==='close'||scene.light;
  const accent=story.accent;
  const foreground=light?ink:paper;
  return <AbsoluteFill style={{background:light?paper:ink,color:foreground,fontFamily:'Nienfos, sans-serif',overflow:'hidden'}}>
    <style>{`@font-face{font-family:Nienfos;src:url('${asset('NotoSans-Regular.ttf')}');font-weight:400}@font-face{font-family:Nienfos;src:url('${asset('NotoSans-Bold.ttf')}');font-weight:700}*{box-sizing:border-box}`}</style>
    {ocean && <><Img src={captureFrame('ocean',f)} style={{position:'absolute',width:'100%',height:'100%',objectFit:'cover',objectPosition:'48% center',opacity:.95}}/><AbsoluteFill style={{background:'linear-gradient(#10252eda, transparent 72%)'}}/></>}
    {ocean && story.id==='08' && <div style={{position:'absolute',top:680,left:130-f*1.3,width:490,height:300,transform:`rotate(${-5+Math.sin(f/24)*4}deg)`}}>
      <Img src={asset('whale-original.svg')} style={{width:410,height:245,objectFit:'contain'}}/>
      <Img src={asset('whale-original.svg')} style={{position:'absolute',width:180,height:110,top:150,left:290,objectFit:'contain'}}/>
      <svg width="540" height="80" style={{position:'absolute',left:10,top:175,opacity:.35}}><path d="M0 15 Q170 50 500 13 M60 35 Q270 70 470 34" stroke="#7f9eaa" fill="none" strokeWidth="1"/></svg>
    </div>}
    {!ocean && scene.layout!=='close' && <div style={{position:'absolute',width:630,height:630,border:'1px solid '+(light?'#cedad5':'#355460'),borderRadius:scene.layout==='split'?'0':'50%',right:-400,top:80,transform:`rotate(${f*.2}deg)`}}/>}
    <AbsoluteFill style={{transform:`translateY(${-end*24}px)`,opacity:1-end*.35}}>
      <div style={{position:'absolute',left:54,right:54,top:83,display:'flex',justifyContent:'space-between',alignItems:'center'}}>
        <span style={{fontWeight:700,fontSize:25,letterSpacing:-1}}>Nienfos</span><span style={{fontSize:15,letterSpacing:2,opacity:.75}}>{scene.layout==='close'?'HABLEMOS':'DISEÑO + DESARROLLO'}</span>
      </div>
      <Heading scene={{...scene,light}} accent={accent}/>
      {scene.layout==='hero' && <div style={{position:'absolute',left:32,right:32,top:650,height:420,borderRadius:22,overflow:'hidden',boxShadow:'0 30px 90px #0005',transform:`translateY(${(1-ease(f,8))*50}px) rotate(${-2+ease(f,8)}deg)`}}><div style={{height:36,background:'#e2e8e5',color:ink,fontSize:15,padding:'7px 20px'}}>● ● ● &nbsp; nienfos.com</div><Img src={captureFrame('hero',f)} style={{width:'100%',height:384,objectFit:'cover',objectPosition:'top'}}/></div>}
      {scene.layout==='browser' && <Browser file={scene.asset!} label={scene.label} height={390}/>}
      {scene.layout==='portfolio' && <><Browser file={scene.asset!} top={565} height={390} label={scene.label} rotate={-2}/><div style={{position:'absolute',right:50,top:775,width:162,height:320,border:'7px solid #172a32',borderRadius:28,overflow:'hidden',boxShadow:'0 15px 60px #0005',transform:`translateY(${(1-ease(f,14))*60}px)`}}><Img src={asset(scene.mobile!)} style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'top'}}/></div></>}
      {(scene.layout==='tiles'||scene.layout==='stack') && <CardList items={scene.items!} accent={accent} light={light} stack={scene.layout==='stack'}/>}
      {scene.layout==='services' && <CardList items={['Webs y catálogos','Software a medida','Integración y automatización']} accent={accent} light={light}/>}
      {scene.layout==='network' && <Network accent={accent}/>}
      {scene.layout==='flow' && <div style={{position:'absolute',left:54,right:54,top:740}}>{scene.items!.map((s,i)=><div key={s} style={{display:'flex',alignItems:'center',gap:25,fontSize:34,marginBottom:32,opacity:ease(f,i*6)}}><span style={{width:60,height:60,borderRadius:30,background:accent,color:ink,display:'grid',placeItems:'center',fontSize:24}}>0{i+1}</span>{s}<span style={{marginLeft:'auto',color:accent}}>↓</span></div>)}</div>}
      {(scene.layout==='step'||scene.layout==='service') && <><div style={{position:'absolute',left:42,bottom:155,fontSize:260,lineHeight:1,fontWeight:700,letterSpacing:-20,color:light?'#c8d6d0':'#385764',transform:`translateX(${(1-ease(f,8))*90}px)`}}>{scene.number}</div><div style={{position:'absolute',bottom:180,right:70,fontSize:90,color:light?ink:accent,transform:`rotate(${ease(f)*-35}deg)`}}>↗</div></>}
      {scene.layout==='type' && <div style={{position:'absolute',left:54,right:54,bottom:230,height:150,display:'flex',gap:14}}>{[1,.7,.45,.25].map((scale,i)=><div key={i} style={{flex:1,background:i===0?(light?ink:accent):(light?'#d8e2dd':'#35545e'),borderRadius:18,transform:`scaleY(${ease(f,8+i*4)*scale})`,transformOrigin:'bottom'}}/>)}</div>}
      {scene.layout==='split' && <div style={{position:'absolute',top:720,left:54,right:54,height:300,display:'flex',gap:18}}><div style={{flex:1,border:'1px dashed #78939c',borderRadius:24,padding:22,display:'flex',flexDirection:'column',gap:20}}>{[0,1,2,3].map(i=><div key={i} style={{height:35,background:'#52717b',borderRadius:7,transform:`translateX(${Math.sin(i+f/30)*12}px)`}}/>)}</div><div style={{flex:1,borderRadius:24,background:accent,padding:26,display:'flex',flexDirection:'column',justifyContent:'space-around'}}>{['Clientes','Tareas','Información'].map(s=><div key={s} style={{color:ink,fontSize:22,borderBottom:'1px solid #1b303850',paddingBottom:12}}>{s} ✓</div>)}</div></div>}
      {scene.layout==='duo' && <><Browser file="chrem-web.webp" top={620} height={265} label="Chrem Propiedades" rotate={-3}/><Browser file="rd-access.webp" top={870} height={240} label="Consultora RD · acceso público" rotate={3}/></>}
      {scene.layout==='close' && <><Img src={asset('logo-primary.png')} style={{position:'absolute',left:48,top:715,width:520,height:185,objectFit:'contain',objectPosition:'left',opacity:ease(f,10)}}/><div style={{position:'absolute',left:54,bottom:220,fontSize:37,letterSpacing:-1,display:'flex',gap:60,alignItems:'center'}}>nienfos.com <span style={{fontSize:55}}>↗</span></div></>}
      <div style={{position:'absolute',left:54,right:54,bottom:78,display:'flex',justifyContent:'space-between',fontSize:14,letterSpacing:1.5,opacity:.7}}><span>TECNOLOGÍA A MEDIDA</span><span>{String(index+1).padStart(2,'0')}</span></div>
    </AbsoluteFill>
  </AbsoluteFill>;
};

const Film:React.FC<{story:Story}>=({story})=>{
  let from=0;
  return <AbsoluteFill>{story.scenes.map((scene,index)=>{
    const start=from;const duration=Math.round(scene.seconds*30);from+=duration;
    return <Sequence key={index} from={start} durationInFrames={duration}><SceneView scene={scene} story={story} index={index}/></Sequence>;
  })}</AbsoluteFill>;
};

export const CampaignRoots:React.FC=()=> <>{stories.map(story=><Composition key={story.id} id={'Nienfos-'+story.id}
  component={Film} defaultProps={{story}} durationInFrames={story.scenes.reduce((n,s)=>n+Math.round(s.seconds*30),0)} fps={30} width={720} height={1280}/>)}</>;
