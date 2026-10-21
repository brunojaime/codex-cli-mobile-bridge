"""Reviewed calm timing for the approved RD narration. No inference or network."""
LEAD=1.4
TAIL=3.2
# Low-energy boundaries inspected in the existing 24 kHz WAVs.
PAUSES={'abrir':[(2.306,1.4)],'documento':[(1.056,1.4)],
        'correo':[(1.50,1.2),(2.841,1.0)],'guardar':[(2.861,1.4)]}
CAPTIONS={'abrir':[(0,2.306,'Desde el cliente, abrí Agregar novedad'),(2.306,4.56,'y elegí la categoría del documento.')],
 'documento':[(0,1.056,'Cargá el archivo'),(1.056,2.92,'y completá su vigencia.')],
 'correo':[(0,1.50,'Elegí los destinatarios'),(1.50,2.841,'y revisá el correo.'),(2.841,5.96,'La plantilla completa los datos por vos.')],
 'guardar':[(0,2.861,'Cuando esté todo listo, tocá Guardar y enviar.'),(2.861,5.56,'La carga continúa en segundo plano.')]}
def at(scene,seconds):
    return LEAD+seconds+sum(pause for cut,pause in PAUSES[scene] if cut<=seconds+1e-8)
def intervals(scene,duration):
    points=[0]+[p[0] for p in PAUSES[scene]]+[duration]
    return [(start,end,at(scene,start)) for start,end in zip(points,points[1:])]
