import React, {useState} from 'react';
import {View, Text, Pressable, Modal, ScrollView, TextInput, Image, Alert, ActivityIndicator} from 'react-native';
import type {NativeFeedbackClient, NativeFeedbackItem} from './native.js';

export interface FeedbackPanelProps {
 client: NativeFeedbackClient;
 title: string;
 capture: () => Promise<{screenshot:string;width:number;height:number;pathname?:string}>;
}

/** Official native UI. Hosts only provide capture/storage ports and identity. */
export function FeedbackPanel({client,title,capture}:FeedbackPanelProps) {
 const [open,setOpen]=useState(false),[shot,setShot]=useState<Awaited<ReturnType<typeof capture>>|null>(null);
 const [comment,setComment]=useState(''),[items,setItems]=useState<NativeFeedbackItem[]>([]);
 const [choices,setChoices]=useState<{id:string;name:string}[]>([]),[preset,setPreset]=useState('');
 const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const [uncertain,setUncertain]=useState(false);
 const action=async(fn:()=>Promise<void>)=>{if(busy)return;setBusy(true);setMessage('');try{await fn();}catch(e){setMessage(e instanceof Error?e.message:'No pudimos completar la operación. La cola se conserva.');}finally{setBusy(false);}};
 const button=(label:string,onPress:()=>void,disabled=false)=><Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={{padding:14,minHeight:48,borderRadius:12,backgroundColor:disabled?'#cbd5e1':'#163c61',marginVertical:5}}><Text style={{color:'white',textAlign:'center',fontWeight:'600'}}>{label}</Text></Pressable>;
 const start=()=>action(async()=>{
  const image=await capture();setItems(await client.pending());setUncertain(await client.legacyUncertain());setShot(image);setComment('');setOpen(true);
  try{const flows=await client.presets();setChoices(flows.presets);setPreset(flows.defaultPresetId||flows.presets[0]?.id||'');}catch{setMessage('Podés guardar sin conexión. Conectate al Bridge para consultar los flujos.');}
 });
 const send=()=>Alert.alert('Enviar a Codex',`Se enviarán ${items.length} capturas y comentarios. No publica la app.`,[{text:'Cancelar',style:'cancel'},{text:'Enviar',onPress:()=>action(async()=>{
  if(shot)throw Error('Guardá o descartá la captura abierta antes de enviar.');
  await client.send(preset);setItems(await client.pending());setMessage('Codex Bridge confirmó la recepción.');
 })}]);
 return <><Pressable accessibilityRole="button" accessibilityLabel="Comentar esta pantalla" onPress={start} disabled={busy} style={{minHeight:44,padding:10,justifyContent:'center'}}><Text style={{color:'#163c61',fontWeight:'600'}}>Feedback</Text></Pressable>
 <Modal visible={open} animationType="slide" onRequestClose={()=>setOpen(false)}><View style={{flex:1,paddingTop:48,backgroundColor:'#eef3f8'}}><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{padding:22,gap:12}}>
 <Text style={{fontSize:26,fontWeight:'700',color:'#172b44'}}>Feedback de desarrollo</Text><Text>{title} · DEV</Text><Text>Revisá la captura. Guardar conserva en este dispositivo; sólo Enviar transmite el lote.</Text>
 {!!message&&<Text accessibilityRole="alert" style={{color:'#9c2c24'}}>{message}</Text>}{busy&&<ActivityIndicator/>}
 {shot&&<><Image accessibilityLabel="Vista previa de la captura" source={{uri:'data:image/png;base64,'+shot.screenshot}} style={{height:260,width:'100%'}} resizeMode="contain"/><TextInput accessibilityLabel="Comentario para Codex" value={comment} onChangeText={setComment} multiline placeholder="¿Qué querés mejorar?" style={{backgroundColor:'white',borderColor:'#cbd5e1',borderWidth:1,borderRadius:12,padding:14,minHeight:100}}/>
 {button('Guardar en la cola',()=>action(async()=>{await client.capture({...shot,comment});setItems(await client.pending());setShot(null);setComment('');}),busy||!comment.trim())}
 {button('Descartar captura',()=>{setShot(null);setComment('');},busy)}</>}
 <Text style={{fontWeight:'700'}}>Pendientes: {items.length}</Text>{items.map((item,index)=><View key={item.id} style={{backgroundColor:'white',padding:12,borderRadius:12}}><Text>{index+1}. {item.comment}</Text>{button('Eliminar comentario '+(index+1),()=>action(async()=>{await client.remove(item.id);setItems(await client.pending());}),busy)}</View>)}
 {choices.map(p=><Pressable key={p.id} accessibilityRole="radio" accessibilityState={{checked:preset===p.id}} onPress={()=>setPreset(p.id)} style={{padding:12,minHeight:48}}><Text>{preset===p.id?'●':'○'} {p.name}</Text></Pressable>)}
 {uncertain&&button('Resolver envío anterior',()=>Alert.alert('Revisar en Codex Mobile','Confirmá el resultado del lote anterior antes de reintentar.',[{text:'Cancelar'},{text:'Ya fue recibido',onPress:()=>action(async()=>{await client.reconcileLegacy('received');setItems(await client.pending());setUncertain(false);})},{text:'No fue recibido',onPress:()=>action(async()=>{await client.reconcileLegacy('not-received');setUncertain(false);})}]),busy)}
 {button('Enviar lote a Codex',send,busy||!items.length||!preset||!!shot||uncertain)}
 {button('Volver a la aplicación',()=>setOpen(false),busy)}
 </ScrollView></View></Modal></>;
}
