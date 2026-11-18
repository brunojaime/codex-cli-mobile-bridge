import React from 'react';
import {AbsoluteFill, Composition, Img, Sequence, interpolate, staticFile, useCurrentFrame} from 'remotion';
import timing from '../public/v20/timing.json';

const ink='#132b34', paper='#f1f0e9', blue='#aacbd1', gold='#c4a979';
const A=(s:string)=>staticFile('campaign/'+s);
const D=(s:string)=>staticFile('presentation-v11/'+s);
const cl={extrapolateLeft:'clamp',extrapolateRight:'clamp'} as const;
const ramp=(f:number,d=0,n=18)=>1-Math.pow(1-interpolate(f,[d,d+n],[0,1],cl),4);
const beat=(s:keyof typeof timing.beats)=>Math.round(timing.beats[s]*30);
const B={question:beat('¿Tu forma'),mess:beat('Mensajes.'),you:beat('Y vos,'),turn:beat('Es hora'),brand:beat('En Nienfos'),listen:beat('Entendemos'),design:beat('Diseñamos'),connect:beat('Conectamos'),proof:beat('De una idea,'),future:beat('Tu negocio ya'),tech:beat('Hagamos'),close:beat('Nienfos. Hablemos')};

const Label:React.FC<{children:React.ReactNode;dark?:boolean}>=({children,dark=false})=><div style={{fontSize:13,letterSpacing:2.5,textTransform:'uppercase',color:dark?ink:blue,fontWeight:400}}>{children}</div>;
const Title:React.FC<{children:React.ReactNode;size?:number;style?:React.CSSProperties}>=({children,size=80,style})=><div style={{fontSize:size,fontWeight:700,letterSpacing:-size*.055,lineHeight:1.04,...style}}>{children}</div>;
const Reveal:React.FC<{children:React.ReactNode;f:number;delay?:number}>=({children,f,delay=0})=><div style={{overflow:'hidden',paddingBottom:8,marginBottom:-8}}><div style={{transform:`translateY(${(1-ramp(f,delay,22))*110}%)`}}>{children}</div></div>;

// A continuously travelling ribbon: one visual thread joins problem, work and brand.
const Ribbon:React.FC<{f:number;light?:boolean;large?:boolean}>=({f,light=false,large=false})=><svg width="1100" height="1000" viewBox="0 0 1100 1000" style={{position:'absolute',left:large?-180:-120,top:large?390:420,transform:`rotate(${-18+Math.sin(f/130)*6}deg) translateY(${-f*.1}px)`,opacity:light?.13:.45}}>
 <defs><linearGradient id="rib" x1="0" y1="0" x2="1" y2="1"><stop stopColor={blue}/><stop offset=".5" stopColor={light?ink:'#416d7c'}/><stop offset="1" stopColor={gold}/></linearGradient></defs>
 {Array.from({length:19},(_,i)=><path key={i} d={`M-100 ${670+i*10} C180 ${780+i*9} 300 ${210+i*9} 600 ${310+i*8} S950 ${690+i*5} 1200 ${240+i*6}`} fill="none" stroke="url(#rib)" strokeWidth={1.2+i*.04}/>)}</svg>;

const Intro=()=>{
 const f=useCurrentFrame();
 return <AbsoluteFill style={{background:ink,color:paper}}>
  <Ribbon f={f}/>
  <div style={{position:'absolute',left:48,top:64}}><Label>NIENFOS / EL PRÓXIMO PASO</Label></div>
  <div style={{position:'absolute',left:46,top:200,right:40}}>
   <Title size={70}>Tu negocio</Title><Title size={140} style={{color:blue,marginTop:8}}>creció.</Title>
   <div style={{height:3,background:gold,marginTop:30,width:interpolate(f,[0,50],[35,610],cl)}}/>
   <div style={{marginTop:46,opacity:ramp(f,B.question-8),transform:`translateY(${(1-ramp(f,B.question-8))*26}px)`}}><Title size={57}>¿Tu forma de<br/>trabajar también?</Title></div>
  </div>
  <div style={{position:'absolute',bottom:102,left:48,display:'flex',alignItems:'center',gap:20}}><div style={{width:32,height:32,borderRadius:32,border:'1px solid '+blue,display:'grid',placeItems:'center',fontSize:23}}>↗</div><span style={{fontSize:17,letterSpacing:.3}}>Para empresas que siguen avanzando.</span></div>
 </AbsoluteFill>
};

const Friction=()=>{
 const f=useCurrentFrame(), global=f+B.mess, you=global>=B.you;
 const words=[{t:'Mensajes.',x:45,y:270,r:-7,d:0},{t:'Planillas.',x:100,y:510,r:5,d:18},{t:'Otra vez.',x:20,y:750,r:-4,d:37}];
 return <AbsoluteFill style={{background:paper,color:ink}}>
  <div style={{position:'absolute',left:48,top:66}}><Label dark>CUANDO TODO DEPENDE DE VOS</Label></div>
  {words.map((w,i)=><div key={w.t} style={{position:'absolute',left:w.x,top:w.y,width:620,height:182,padding:'35px 30px',background:i===1?ink:blue,color:i===1?paper:ink,boxShadow:'0 25px 45px #132b3418',opacity:you?.18:1,transform:`translateY(${(1-ramp(f,w.d,13))*550}px) rotate(${w.r}deg)`}}><Title size={79}>{w.t}</Title><div style={{height:2,background:'currentColor',opacity:.3,width:150,marginTop:13}}/></div>)}
  {you&&<div style={{position:'absolute',left:48,right:48,top:470,opacity:ramp(global,B.you,9)}}><Title size={96}>Y vos,<br/>en el medio.</Title><div style={{width:70,height:5,background:gold,marginTop:38}}/></div>}
 </AbsoluteFill>
};

const Turn=()=>{
 const f=useCurrentFrame();
 return <AbsoluteFill style={{background:ink,color:paper}}><Ribbon f={f+200}/>
  <div style={{position:'absolute',left:48,right:40,top:325}}><Label>HAY OTRA FORMA DE AVANZAR</Label><div style={{marginTop:45}}><Reveal f={f}><Title size={90}>El próximo</Title></Reveal><Reveal f={f} delay={5}><Title size={142} style={{color:blue}}>paso.</Title></Reveal></div></div>
  <div style={{position:'absolute',left:48,bottom:230,width:620,height:2,background:'#aacbd140'}}><div style={{height:2,width:620*ramp(f,5,45),background:gold}}/></div>
 </AbsoluteFill>
};

const Craft=()=>{
 const f=useCurrentFrame(),g=f+B.brand;
 const mode=g>=B.connect?3:g>=B.design?2:g>=B.listen?1:0;
 const headlines=[<>Webs y<br/>software.<br/><span style={{color:blue}}>A tu medida.</span></>,<>Entender<br/><span style={{color:blue}}>tu negocio.</span></>,<>Diseñar<br/><span style={{color:blue}}>con vos.</span></>,<>Conectar<br/><span style={{color:blue}}>lo que hacés.</span></>];
 const labels=['TECNOLOGÍA CON CRITERIO','PRIMERO, ESCUCHAR','DISEÑO QUE SE TRABAJA JUNTOS','INTEGRACIÓN CON PROPÓSITO'];
 const start=[B.brand,B.listen,B.design,B.connect][mode];
 return <AbsoluteFill style={{background:ink,color:paper}}>
  <div style={{position:'absolute',left:48,top:65}}><Label>{labels[mode]}</Label></div>
  <div key={mode} style={{position:'absolute',left:48,right:38,top:185,transform:`translateY(${(1-ramp(g,start,12))*24}px)`,opacity:ramp(g,start,10)}}><Title size={77}>{headlines[mode]}</Title></div>
  <div style={{position:'absolute',left:-65,top:mode===0?660:620,width:850,height:545,transform:`perspective(1400px) rotateY(${-12+f*.075}deg) rotateX(7deg) rotateZ(-5deg) translateX(${-f*.14}px)`,boxShadow:'0 40px 90px #0007',border:'1px solid #aacbd14a',overflow:'hidden',background:paper}}>
   <div style={{height:32,background:'#e2e7e2',padding:'8px 18px',fontSize:12,color:ink}}>nienfos.com</div><Img src={D('desktop.png')} style={{width:'100%',height:540,objectFit:'cover',objectPosition:'top'}}/>
   {mode===1&&<div style={{position:'absolute',inset:0,background:'#132b34dc',padding:'75px 120px',color:paper}}><Label>EL PUNTO DE PARTIDA</Label><Title size={54} style={{marginTop:36}}>Tu equipo.<br/>Tu operación.<br/>Tu próximo desafío.</Title><div style={{height:2,background:gold,width:360,marginTop:30}}/></div>}
   {mode===2&&<div style={{position:'absolute',inset:0,pointerEvents:'none',backgroundImage:'linear-gradient(#aacbd133 1px, transparent 1px),linear-gradient(90deg,#aacbd133 1px,transparent 1px)',backgroundSize:'70px 70px',border:'16px solid #aacbd140'}}/>}
  </div>
  {mode===3&&<div style={{position:'absolute',width:205,height:415,right:40,top:720,background:ink,border:'5px solid #78949b',borderRadius:30,padding:6,overflow:'hidden',boxShadow:'0 20px 50px #0008',transform:`translateY(${(1-ramp(g,B.connect,16))*160}px) rotate(5deg)`}}><Img src={D('mobile.png')} style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'top',borderRadius:20}}/></div>}
  <div style={{position:'absolute',bottom:77,left:48,right:48,display:'flex',gap:8}}>{[0,1,2,3].map(i=><div key={i} style={{height:3,flex:1,background:i<=mode?blue:'#aacbd12b'}}/>)}</div>
 </AbsoluteFill>
};

const Proof=()=>{
 const f=useCurrentFrame();
 return <AbsoluteFill style={{background:paper,color:ink}}>
  <div style={{position:'absolute',left:48,top:65}}><Label dark>DEL CONCEPTO A LO CONCRETO</Label></div>
  <div style={{position:'absolute',left:48,top:160}}><Title size={79}>Proyectos<br/>reales.</Title></div>
  <div style={{position:'absolute',left:48,top:420,width:880,height:590,overflow:'hidden',boxShadow:'0 30px 60px #132b3430',transform:`perspective(1400px) rotateY(-13deg) rotateZ(-5deg) translateX(${-f*.52}px)`}}><Img src={A('chrem-web.webp')} style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'top'}}/></div>
  <div style={{position:'absolute',right:45,top:665,width:218,height:410,borderRadius:27,border:'5px solid '+ink,overflow:'hidden',boxShadow:'0 24px 65px #132b3460',transform:`rotate(6deg) translateY(${(1-ramp(f,7))*110}px)`,background:ink}}><Img src={A('rd-mobile.webp')} style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'top'}}/></div>
  <div style={{position:'absolute',left:48,bottom:90}}><div style={{fontSize:21,fontWeight:700}}>Chrem Propiedades · RD Gestión HSE</div><div style={{fontSize:16,marginTop:12,color:'#4c666e'}}>Web y software de gestión / portfolio Nienfos</div></div>
 </AbsoluteFill>
};

const Future=()=>{
 const f=useCurrentFrame(),g=f+B.future;
 return <AbsoluteFill style={{background:ink,color:paper}}><Ribbon f={f+450} large/>
  <div style={{position:'absolute',left:48,top:68}}><Label>DISEÑO / DESARROLLO / INTEGRACIÓN</Label></div>
  <div style={{position:'absolute',left:48,right:40,top:250}}><Reveal f={f}><Title size={79}>A la altura</Title></Reveal><Reveal f={f} delay={3}><Title size={79}>de lo que</Title></Reveal><Reveal f={f} delay={6}><Title size={142} style={{color:blue}}>viene.</Title></Reveal></div>
  <div style={{position:'absolute',left:48,top:820,width:580,fontSize:28,lineHeight:1.4,opacity:ramp(g,B.tech)}}>Que la tecnología acompañe<br/>el movimiento de tu negocio.</div>
 </AbsoluteFill>
};

const Close=()=>{
 const f=useCurrentFrame();
 return <AbsoluteFill style={{background:paper,color:ink}}>
  <div style={{position:'absolute',left:48,top:66}}><Label dark>EL PRÓXIMO PASO, JUNTOS.</Label></div>
  <div style={{position:'absolute',left:48,top:240,opacity:ramp(f,0,12)}}><Img src={A('logo-primary.png')} style={{width:590,height:190,objectFit:'contain',objectPosition:'left'}}/></div>
  <div style={{position:'absolute',left:48,right:42,top:560}}><Title size={69}>Hablemos de<br/>tu próximo paso.</Title><div style={{height:2,background:ink,marginTop:48,transform:`scaleX(${ramp(f,10,32)})`,transformOrigin:'left'}}/></div>
  <div style={{position:'absolute',left:48,right:48,top:930,display:'flex',justifyContent:'space-between',alignItems:'center',fontSize:42,letterSpacing:-1}}><span>nienfos.com</span><div style={{width:80,height:80,borderRadius:80,background:ink,color:paper,display:'grid',placeItems:'center',fontSize:48,transform:`rotate(${-30+30*ramp(f,5,30)}deg)`}}>↗</div></div>
  <div style={{position:'absolute',left:48,bottom:88,fontSize:16,letterSpacing:2,color:'#49636b'}}>WEBS Y SOFTWARE A MEDIDA</div>
 </AbsoluteFill>
};

const Film=()=>{
 const scenes=[{from:0,to:B.mess,C:Intro},{from:B.mess,to:B.turn,C:Friction},{from:B.turn,to:B.brand,C:Turn},{from:B.brand,to:B.proof,C:Craft},{from:B.proof,to:B.future,C:Proof},{from:B.future,to:B.close,C:Future},{from:B.close,to:timing.frames,C:Close}];
 return <AbsoluteFill style={{background:ink}}><style>{`@font-face{font-family:Nienfos;src:url('${A('NotoSans-Regular.ttf')}');font-weight:400}@font-face{font-family:Nienfos;src:url('${A('NotoSans-Bold.ttf')}');font-weight:700}*{box-sizing:border-box}`}</style><div style={{width:720,height:1280,position:'absolute',transform:'scale(1.5)',transformOrigin:'top left',fontFamily:'Nienfos,sans-serif'}}>{scenes.map(({from,to,C})=><Sequence key={from} from={from} durationInFrames={to-from}><C/></Sequence>)}</div></AbsoluteFill>
};
export const ProposalV20Root=()=> <Composition id="NienfosV20" component={Film} durationInFrames={timing.frames} fps={30} width={1080} height={1920}/>;
