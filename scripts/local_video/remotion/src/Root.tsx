import React from 'react';
import {AbsoluteFill, Composition, Img, Sequence, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {Modern} from './Modern';
import {CampaignRoots} from './Campaign';
import {CampaignProRoots} from './CampaignPro';
import {PresentationRoot} from './Presentation';
import {PresentationV4Root} from './PresentationV4';
import {PresentationV5Root} from './PresentationV5';

const ink = '#1c323b';
const teal = '#80a1a9';
const paper = '#f4f2eb';
const ease = (frame: number, start = 0) => {
  const t = interpolate(frame, [start, start + 26], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return 1 - Math.pow(1 - t, 3);
};

const Scene: React.FC<{index: number}> = ({index}) => {
  const f = useCurrentFrame();
  const enter = ease(f);
  const titles = [<>Las ideas<br/>merecen<br/><span style={{color: teal}}>tomar forma.</span></>, <>Menos fricción.<br/><span style={{color: teal}}>Más posibilidades.</span></>, <>Pensar.<br/>Diseñar.<br/><span style={{color: teal}}>Construir.</span></>, <>Tu próximo<br/>paso empieza<br/><span style={{color: teal}}>con una idea.</span></>];
  const captions = ['Cada proyecto empieza con una idea.', 'Una mirada simple para desafíos complejos.', 'De la primera conversación a una solución con sentido.', 'Conversemos sobre lo que viene.'];
  const dark = index === 1 || index === 2;
  const color = dark ? paper : ink;
  return <AbsoluteFill style={{backgroundColor: dark ? ink : paper, color, padding: '86px 58px', fontFamily: 'Arial, sans-serif'}}>
    <div style={{display: 'flex', justifyContent: 'space-between', fontSize: 15, letterSpacing: 3, color: dark ? '#a9c0c5' : '#62777e'}}>
      <span>NIENFOS / IDEAS EN MOVIMIENTO</span><span>0{index + 1}</span>
    </div>
    <div style={{position: 'absolute', right: -150, top: 155, width: 480, height: 480, border: `1px solid ${dark ? '#58717b' : '#c4ceca'}`, borderRadius: '50%', transform: `translateY(${Math.sin(f / 70) * 20}px)`}}/>
    <div style={{position: 'absolute', right: -95, top: 210, width: 370, height: 370, border: `1px solid ${dark ? '#58717b' : '#c4ceca'}`, borderRadius: '50%'}}/>
    <div style={{position: 'relative', marginTop: 170, fontSize: index === 1 ? 72 : 78, lineHeight: 1.06, letterSpacing: -4, fontWeight: 700, transform: `translateY(${(1-enter)*28}px)`}}>{titles[index]}</div>
    <div style={{height: 5, width: 72 + ease(f, 15) * 120, background: teal, marginTop: 48}}/>
    <div style={{fontSize: 27, lineHeight: 1.45, maxWidth: 540, marginTop: 38, opacity: ease(f, 15), transform: `translateY(${(1-ease(f,15))*15}px)`}}>{captions[index]}</div>
    {index === 2 && <div style={{display: 'flex', gap: 12, marginTop: 58}}>{['01 / Visión', '02 / Diseño', '03 / Acción'].map((s,i)=><div key={s} style={{border:`1px solid #58717b`, padding:'18px 13px', fontSize:17, opacity:ease(f,25+i*12)}}>{s}</div>)}</div>}
    {index === 3 && <Img src={staticFile('nienfos.png')} style={{position: 'absolute', bottom: 180, left: 58, width: 360, height: 125, objectFit: 'contain'}}/>}
    <div style={{position: 'absolute', bottom: 88, left: 58, right: 58, display: 'flex', justifyContent:'space-between', fontSize:15, letterSpacing:2, color:dark?'#a9c0c5':'#62777e'}}><span>PROPUESTA INSTITUCIONAL</span><span>BORRADOR 01</span></div>
  </AbsoluteFill>;
};

const Institutional: React.FC = () => {
  const f = useCurrentFrame();
  return <AbsoluteFill>
    {[0,1,2,3].map(i=><Sequence key={i} from={i*180} durationInFrames={180}><Scene index={i}/></Sequence>)}
    {[180,360,540].map(start=><AbsoluteFill key={start} style={{backgroundColor:teal, transform:`translateX(${interpolate(f,[start-10,start,start+10],[100,0,-100],{extrapolateLeft:'clamp',extrapolateRight:'clamp'})}%)`, opacity: f>=start-10 && f<=start+10 ? 1:0}}/>)}
    <div style={{position:'absolute',bottom:0,left:0,height:5,width:`${(f/719)*100}%`,backgroundColor:teal}}/>
  </AbsoluteFill>;
};

export const Root: React.FC = () => <>
  <Composition id="Institucional" component={Institutional} durationInFrames={720} fps={30} width={720} height={1280}/>
  <Composition id="InstitucionalAgil" component={Modern} durationInFrames={420} fps={30} width={720} height={1280}/>
  <CampaignRoots/>
  <CampaignProRoots/>
  <PresentationRoot/>
  <PresentationV4Root/>
  <PresentationV5Root/>
</>;
