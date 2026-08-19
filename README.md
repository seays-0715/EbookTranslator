# EbookTranslator

Japanese EPUB → Traditional Chinese EPUB desktop translator.

## Workflow

1. Select an EPUB.
2. Extract stable-ID TXT files.
3. Translate the TXT files manually with your preferred AI or translation tool.
4. Put the translated TXT files back into the translation folder.
5. Validate the translation files.
6. Rebuild and package a compact EPUB.

## Manual translation

The application does not require an API key or built-in AI translation service. Use ChatGPT, Claude, Gemini, Grok, or another translation tool of your choice, while preserving the program-generated paragraph IDs.

## Supported source languages

The main use case is Japanese → Traditional Chinese, but the extraction and rebuild pipeline is not limited to Japanese source EPUBs. The output is intended to be Traditional Chinese.
