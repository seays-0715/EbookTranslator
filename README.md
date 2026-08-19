# EbookTranslator

Japanese EPUB → Traditional Chinese EPUB desktop translator.

## Workflow

1. Select an EPUB.
2. Extract stable-ID TXT files.
3. Translate manually with any LLM, or use the built-in OpenAI-compatible API mode.
4. Validate IDs, completeness, empty translations, and Japanese residue.
5. Rebuild and package a compact EPUB.

## API mode

The API translator uses an OpenAI-compatible `chat/completions` endpoint. The default endpoint is OpenAI's API, but `API Base URL` can be changed for compatible providers.

- API key is entered at runtime and is not written to the repository or a config file.
- Translation requests preserve program-generated paragraph IDs.
- Large TXT files are split automatically at paragraph boundaries using the configured batch character limit.
- API responses are rejected if IDs/order are wrong, a translation is empty, or Japanese residue remains.

## Manual mode

The existing manual workflow remains available and does not require an API key.
