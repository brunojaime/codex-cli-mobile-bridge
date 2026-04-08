# OneNote Graph Endpoints

## Discovery

- `GET /me`
- `GET /me/onenote/notebooks`
- `GET /me/onenote/sections`
- `GET /me/onenote/notebooks/{notebook-id}/sections`
- `GET /me/onenote/pages`
- `GET /me/onenote/sections/{section-id}/pages`

Use the page-listing endpoints to discover page IDs before append or attach operations.

## Inspect Page Content

- `GET /me/onenote/pages/{page-id}/content`
- `GET /me/onenote/pages/{page-id}/content?includeIDs=true`

Use `includeIDs=true` when you need stable element IDs for targeted page updates.

## Create Pages

- `POST /me/onenote/sections/{section-id}/pages`

Use `text/html` when the request contains only HTML or plain text converted to HTML.

Use `multipart/form-data` when the request contains binary images or file attachments. The request must include:

- a `Presentation` part with `text/html`
- one binary part per image or file

Images are referenced from the HTML using:

```html
<img src="name:imageBlock1" alt="Example image" />
```

Files are referenced from the HTML using:

```html
<object data-attachment="Report.pdf" data="name:fileBlock1" type="application/pdf"></object>
```

## Update Pages

- `PATCH /me/onenote/pages/{page-id}/content`

Use `application/json` when the update contains no binary payload.

Use `multipart/form-data` when the update includes binary content. The request must include:

- a `Commands` part with `application/json`
- one binary part per image or file

The skill uses `body` as the default append target for simple updates.
