# English user guide

## Setup and language

Extract the entire ZIP to a writable folder and run `口播快剪.exe`. Do not move only the EXE. Initial downloads require access to Hugging Face, GitHub and PyPI; retry after resolving connection failures. Install your own Jianying or Premiere to open exports.

The header language switch also selects recognition language. It does not automatically handle mixed-language audio. English and Chinese maintain separate project lists and transcript caches; switching does not overwrite existing projects. English downloads its own model. Jianying and Premiere project lists are also separate. AE is a placeholder.

`runtime/` contains code/dependencies; `data/` contains projects, models, downloaded tools and caches. Back up data and original media before upgrading. Media is referenced by its original path. Clearing project data loses review work; clearing caches after exiting may require regenerating previews.

## Transcribe and review

1. Choose an editor, enter the local video path, and import.
2. Download speech and speaker models. Run the one-click local workflow with your current settings. It transcribes and groups voices; it does not invoke AI sentence correction.
3. A/B are anonymous acoustic groups, not verified identities. Audition uncertain/overlapping speech and correct speaker labels using selected words.
4. Review sentence breaks and text locally. Use short natural phrases. The AI target is about nine English words (about nine Chinese characters), not a rigid limit.
5. Only after manual review, optionally invoke the separate AI correction action. It should preserve speaker labels and timing, correct spelling, split sentences and identify hesitation ranges. Audition the result before accepting suggestions.

## Optional AI

Enter your own DeepSeek key and model in Settings. Keys stay in memory and must be re-entered after restarting. Do not include keys in shared data. Provider compatibility depends on its current API configuration.

Extract topic returns a suggested title, main topic, concise summary and key points. Edit/copy them on the page; this action does not change cuts.

Information retention analyzes the **whole transcript**, not just existing deletion suggestions. 20% is strongest condensation; 100% requests no additional condensation. This is an approximate content/text retention target, not an exact output-duration promise. Review suggested removals; select all or deselect as needed.

## Export

Enable manual-review direct cutting to slice at the current reviewed boundaries without an additional AI pass. Review export keeps a full-length black base, with kept dialogue, no-content/hesitations and deletion suggestions on separate overlay tracks. Direct deletion removes selected ranges and compacts retained video and captions using the same timing map. Keep a review copy first.

Set a meaningful project name and choose captions. For Jianying, provide its actual draft folder and open the newly generated draft in Jianying 5.9.

For Premiere, download and fully extract the exchange ZIP, import its XML into Premiere, then open the sequence. Keep the PNG caption folder and source video available. Relink missing media if necessary. PNG captions render visually but are not editable native captions. Import SRT separately if desired; hard binding to video is not provided.

## Close gaps after fine edits

Save your edits first. Select the Jianying draft folder, or export FCP XML from Premiere and select that XML. Run Close gaps and open the new copy. Video and captions share a time map; captions shorter than their clip retain their original offset. Do not independently align every caption. Unsupported transitions, nesting, speed changes and other complex structures are rejected; simplify a copy before retrying.

For reports, include version, reproducible steps and redacted logs. Never publish your media, transcript, API key or personal project folder.
