# VocBuilderAI for Anki

## Description:
[Taiwan language version](README_ZH_TW.md)
VocabBuilderAI is an Anki add-on that integrates OpenAI's GPT-3.5 Turbo and Whisper API to enhance the vocabulary learning experience. It allows users to generate comprehensive flashcards for new words, including definitions, pronunciations, etymology, synonyms, antonyms, and real-world examples.

Besides OpenAI, you can also use Groq, Ollama, OpenRouter and other OpenAI-compatible services.

- ![](media/dictionary.png)
- ![](media/webster.png)
## Features:
- Generates comprehensive flashcards for vocabulary learning
- Integrates OpenAI GPT-3.5 Turbo for detailed definitions and examples (customizable models)
- Uses OpenAI's text-to-speech model for audio pronunciation (more realistic pronunciation)
- Allows customization of default decks, flashcard types, and tags
- Integrates seamlessly with Anki's new flashcard creation

![demo](media/vocAI-demo-1.gif)
## Installation:
- Download from AnkiWeb or GitHub
- Install using the provided code or installation file
- Configure the add-on settings in Anki, including OpenAI API keys

### Node Type
create a node type called "vocbuilderAI" with following fields:
- Vocabulary
- Detail definition
- Pronunciations
- Sound
- Etymology, Synonyms, and Antonyms
- Real-world examples
## Usage:

- Open a new flashcard window in Anki
- Click the "VocabBuilderAI" button or select the option from the menu
- Enter a new word, and the add-on will generate a comprehensive flashcard

  ![screenshot1](media/sceenshot-1.png)
  ![screenshot2](media/sceenshot-2.png)
  ![screenshot3](media/sceenshot-3.png)

## Configuration:

- OpenAI API key: for accessing OpenAI services
- Default deck: for adding new flashcards when no deck is specified
- Default flashcard type: for new words
- Audio options: for selecting the text-to-speech engine

## Support:
For support, questions, or feature requests, please visit the GitHub repository or contact the add-on author.