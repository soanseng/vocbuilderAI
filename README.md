# VocabBuilderAI for Anki

## Description:
[Taiwan language version](README_ZH_TW.md)
VocabBuilderAI is an Anki add-on designed to enhance vocabulary learning by leveraging OpenAI's GPT-3.5 Turbo and Whisper APIs. It allows users to generate detailed notes for new vocabulary words, complete with definitions, pronunciations, etymologies, synonyms, antonyms, and real-world examples.

## Features:
    - Generate comprehensive vocabulary notes.
    - Integrate with OpenAI's GPT-3.5 Turbo for detailed definitions and examples.
    - Use OpenAI's TTS (text-to-speech) model for pronunciation audio.
    - Customizable settings for default deck, note type, and tags.
    - User-friendly interface integrated into Anki's Add Note window.

## Installation:

    - Download the add-on from the AnkiWeb or GitHub repository.
    - Install it in Anki using the provided code or installation file.
    - Configure the add-on settings, including the OpenAI API key, in Anki's Add-on menu.

## Usage:

    - Open the Add Note window in Anki.
    - Click on the "VocabBuilderAI" button or menu item.
    - Enter a new vocabulary word and the add-on will generate the complete note.

## Configuration:

    - OpenAI API Key: Required for accessing OpenAI services.
    - Default Deck: The deck where new notes will be added if not specified.
    - Default Note Type: The note type used for new vocabulary notes.
    - Speech Voice: Select the voice for TTS audio.

## Support:
For support, questions, or feature requests, please visit the GitHub repository or contact the add-on author.
## TODO
- [ ] add japanese vocabulary learning
- [ ] at installation, check there is a vocbuilderAI note type or not, creating it for users automatically
- [ ] use git submodule to load into libs for necessary packages
- [ ] check this word is repeated? if repeated add tags or rewrite its content or not
- [ ] after adding voice to anki, delete it on the addon folder
- [ ] add type to it for better development