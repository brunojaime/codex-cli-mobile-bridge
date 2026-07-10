---
id: 016-diagram-mcp-rendering-engine
title: Diagram MCP Rendering Engine
status: implemented
type: feature
domains:
  - diagramming
  - mcp
  - rendering
  - editor
---

# Diagram MCP Rendering Engine

## Intent

Crear un sistema de generación, renderizado y edición inicial de diagramas de componentes UML donde un agente pueda producir un diagrama desde lenguaje natural, renderizarlo con reglas visuales determinísticas, y permitir que el usuario lo ajuste manualmente en una grilla visual.

El objetivo es combinar tres capacidades:

1. Generación inicial estilo PlantUML, donde el usuario describe una arquitectura y el sistema infiere una disposición razonable.
2. Renderizado determinístico con templates propios, incluyendo componentes UML e interfaces Provided/Required con socket del lado consumidor y lollipop del lado proveedor.
3. Edición visual estilo Draw.io acotada al dominio, permitiendo mover elementos, fijar posiciones, recalcular conexiones y exportar el resultado.

El MCP Server será la interfaz formal para que el agente cree, modifique, valide, renderice y exporte diagramas. El MCP Server debe correr por HTTPS en localhost.

## Scope

Incluye:

1. Un contrato `DiagramSpec` como fuente de verdad del diagrama.
2. Un MCP Server local expuesto por HTTPS.
3. Tools MCP para crear, validar, modificar, mover, renderizar y exportar diagramas.
4. Un engine desacoplado del frontend que genere SVG determinístico.
5. Templates oficiales para:
   1. `uml_component`
   2. `provided_required_interface`
   3. conectores entre anchors
6. Layout automático inicial para diagramas de componentes izquierda a derecha.
7. Anchors y puertos dinámicos para unir elementos desde puntos correctos.
8. Router de líneas ortogonales simple.
9. Modelo de posiciones manuales con `pinned: true`.
10. Integración conceptual con editor visual basado en grilla, drag, snap y rerender.
11. Validaciones semánticas y estructurales antes del render.
12. Exportación inicial a SVG.
13. Preparación para exportación posterior a PNG y PDF.

## Non-Goals

Queda explícitamente afuera:

1. Crear un clon completo de Draw.io.
2. Soportar todos los tipos de diagramas UML.
3. Soportar shapes arbitrarios definidos por el usuario en el MVP.
4. Edición visual colaborativa multiusuario en tiempo real.
5. Routing avanzado con optimización global de cruces complejos.
6. Importación completa de archivos `.drawio`.
7. Dependencia de Mermaid o PlantUML como renderer final.
8. Generación de SVG libre por parte del LLM.
9. Uso de mock data, demo mode o placeholder URLs para releases productivos.
10. Publicación remota del MCP Server fuera de localhost en el MVP.

## Functional Contract

El sistema debe operar con esta separación de responsabilidades:

1. El agente interpreta lenguaje natural y produce un `DiagramSpec`.
2. El MCP Server expone tools para manipular el `DiagramSpec`.
3. El Diagram Engine valida, normaliza, calcula layout y renderiza.
4. El Renderer produce SVG final.
5. El editor visual muestra SVG y mantiene interacciones de usuario.
6. El frontend no implementa lógica UML de dibujo. Solo muestra SVG y reporta operaciones de edición.

El agente no debe decidir geometría interna de componentes, sockets, lollipops, íconos o conectores. Esa responsabilidad pertenece al Diagram Engine y a su Template Registry.

## DiagramSpec Contract

`DiagramSpec` es la fuente de verdad persistible y versionable.

Estructura mínima:

