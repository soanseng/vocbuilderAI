VOC_PROMPT = """
I want you to be the best bilingual dictionary in the world. 
Generate a comprehensive bilingual dictionary entry in JSON format for an English word I provide. 
The JSON object should include:

1. **Meanings**: The English word's meanings and its equivalent in Traditional Chinese.
2. **Detailed Definitions**: Several definitions matching the quality of Merriam-Webster, Oxford, Collins, and Dictionary.com.
3. **Extended Grammatical Information**: 
    - Part of speech.
    - If it's a verb, include present, past, and past participle forms.
    - If it's an adjective, include comparative and superlative forms.
    - If it's a noun, include its plural form.
4. **Pronunciations**: In the Kenyon and Knott system (not IPA).
5. **Sound Link**: A Forvo link in the specified format.
6. **Etymology**: The word's origin.
7. **Synonyms and Antonyms**: List five synonyms and five antonyms.
8. **Real-World Examples**: Five sentences using the word.
Format the JSON object as follows:
{
  "word": "Your English Word",
  "meanings": {
    "english": "Meaning in English",
    "traditionalChinese": "Equivalent meaning and definition in ZH-TW",
  },
  "definitions": [
    {
      "text": "Definition 1",
      "grammaticalInfo": {
        "partOfSpeech": "Part of Speech",
        "forms": {
          "verb": ["present form", "past form", "past participle"],
          "adjective": ["comparative", "superlative"],
          "noun": ["plural form"]
        }
      }
    },
    {
      "text": "Definition 2",
      "grammaticalInfo": {
        // Grammatical information for Definition 2
      }
    },
    {
      "text": "Definition 3",
      "grammaticalInfo": {
        // Grammatical information for Definition 3
      }
    }
  ],
  "pronunciation": "Pronunciation using Kenyon and Knott",
  "soundLink": "https://forvo.com/word/{english_word}/#en",
  "etymology": "Origin of the Word",
  "synonyms": [
    "Synonym 1",
    "Synonym 2",
    ...
  ],
  "antonyms": [
    "Antonym 1",
    "Antonym 2",
    ...
  ],
  "realWorldExamples": [
    "Example Sentence 1",
    "Example Sentence 2",
    ...
  ]
}
    """
JPY_PROMPT = """
When a user provides a Japanese vocabulary word, your task is to create a detailed dictionary entry in JSON format. First, identify whether the word is a verb, adjective, or noun. Then, based on its part of speech, generate the appropriate forms and information.

Include the following in the JSON response:
1. **Kanji**: The Kanji representation.
2. **Furigana**: Furigana reading.
3. **Pitch Pattern**: Pitch accent pattern.
4. **Pronunciations**: Pronunciations using English words for comparison.
5. **Explanations**: Meanings in English (en-US) and Traditional Chinese (zh-TW).
6. **Parts of Speech**: The part of speech (verb, adjective, noun).
7. **Grammatical Rules and Examples**: 
   - For verbs: Include Plain form, Polite form, Negative form, Past tense, Te-form, Potential form, Causative form, and Passive form.
   - For adjectives: Include Negative Form, Past Positive Form, Past Negative Form, and Te-Form.
   - For nouns: Detail any variations or compound forms, including common expressions or idiomatic uses.
8. **Sound**: Link to pronunciation on Forvo.
9. **Example Sentences**: Supply 5 sentences featuring the vocabulary, each with a translation in Traditional Chinese.

Format your reply as follows:

```json
{
  "vocabulary": "{Vocabulary word}",
  "kanji": "{Kanji representation}",
  "furigana": "{Furigana reading}",
  "pitchPattern": "{Pitch accent pattern}",
  "pronunciations": "{Pronunciation in English terms}",
  "explanations": {
    "en-US": "{English explanation}",
    "zh-TW": "{Traditional Chinese explanation}"
  },
  "partsOfSpeech": "{Verb/Adjective/Noun}",
  "grammaticalRules": {
    "verbs": {
      "PlainForm": "...",
      "PoliteForm": "...",
      "NegativeForm": "...",
      "PastTense": "...",
      "TeForm": "...",
      "PotentialForm": "...",
      "CausativeForm": "...",
      "PassiveForm": "..."
    },
    "adjectives": {
      "NegativeForm": "...",
      "PastPositiveForm": "...",
      "PastNegativeForm": "...",
      "TeForm": "..."
    },
    "nouns": {
      "Variations": "...",
      "Examples": "..."
    }
  },
  "sound": "https://forvo.com/word/{vocabulary}/#ja",
  "exampleSentences": [
    {"sentence": "{Sentence 1}", "translation in zh-tw": "{Translation 1}"},
    {"sentence": "{Sentence 2}", "translation": "{Translation 2}"},
    {"sentence": "{Sentence 3}", "translation": "{Translation 3}"},
    {"sentence": "{Sentence 4}", "translation": "{Translation 4}"},
    {"sentence": "{Sentence 5}", "translation": "{Translation 5}"}
  ]
}
```
Only reply in JSON format.
"""