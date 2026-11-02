import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from source_separation_claim_audit.audit import audit, evidence, main, phrases_in
from source_separation_claim_audit import phrases

EXPECTED_SEPARATION = ('audio source separation', 'separates audio sources', 'separate audio sources', 'stem separation', 'separates stems', 'separate stems', 'vocal separation', 'separates vocals', 'separate vocals', 'isolates vocals', 'vocal isolation', 'isolates vocal tracks', 'instrument separation', 'separates instruments', 'separate instruments', 'isolates instruments', 'music source separation', 'separates music sources', 'audio stem separation', 'source separation', 'separates sources', 'separate sources', 'stem extraction', 'extracts stems', 'vocal extraction', 'extracts vocals', 'instrumental separation', 'isolates drums', 'isolates bass', 'drum separation', 'bass separation', 'vocal removal', 'removes vocals', 'backing track separation', 'separates backing tracks', 'audio demixing', 'demixes audio', 'separates audio into stems', 'splits audio into stems', 'audio track separation', 'separates audio tracks', 'isolates individual instruments', 'supports source separation')
EXPECTED_NOSEPARATION = ('no source separation', 'does not separate audio sources', 'without source separation', 'no stem separation', 'does not separate stems', 'without stem separation', 'no vocal separation', 'does not separate vocals', 'without vocal separation', 'no vocal isolation', 'does not isolate vocals', 'source separation not supported', 'does not support source separation', 'cannot separate stems', 'never separates stems', 'no instrument separation', 'does not separate instruments', 'no vocal extraction', 'does not extract vocals', 'no stem extraction', 'does not extract stems', 'without vocal isolation', 'no audio source separation', 'does not isolate instruments')

class AuditTests(unittest.TestCase):
    def fixture(self, claim='separates stems', files=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / 'README.md').write_text(claim)
        for name, source in (files or {}).items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
        return root

    def cli(self, root, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            try:
                code = main([str(root)] + list(args))
            except SystemExit as error:
                code = error.code
        return code, out.getvalue()

    def test_phrase_oracle(self):
        self.assertEqual(phrases.SEPARATION, EXPECTED_SEPARATION)
        self.assertEqual(phrases.NOSEPARATION, EXPECTED_NOSEPARATION)
        self.assertEqual(len(phrases.SEPARATION), 43)
        self.assertEqual(len(phrases.NOSEPARATION), 24)

    def test_all_phrases(self):
        for phrase in EXPECTED_SEPARATION:
            with self.subTest(phrase=phrase):
                self.assertEqual(phrases_in(phrase), {'SEPARATION'})
        for phrase in EXPECTED_NOSEPARATION:
            with self.subTest(phrase=phrase):
                self.assertEqual(phrases_in(phrase), {'NOSEPARATION'})

    def test_bad(self):
        root = self.fixture()
        code, out = self.cli(root, '--json')
        result = json.loads(out)
        self.assertEqual(code, 2)
        self.assertEqual(result['verdict'], 'FAIL')
        self.assertEqual(result['findings'][0]['id'], 'documented-source-separation-claim-false')
        self.assertEqual(result['findings'][0]['severity'], 'HIGH')
        self.assertTrue(result['findings'][0]['message'])

    def test_good(self):
        self.assertEqual(self.cli(self.fixture(files={'app.py': 'x.separate_stems()'}))[0], 0)

    def test_denial(self):
        root = self.fixture('does not separate stems', {'app.py': 'x.separate_stems()'})
        self.assertEqual(self.cli(root)[0], 2)
        self.assertEqual(audit(root)['findings'][0]['id'], 'documented-no-source-separation-claim-false')
        self.assertEqual(audit(root)['findings'][0]['severity'], 'HIGH')

    def test_no_claim(self):
        self.assertEqual(audit(self.fixture('Hello'))['verdict'], 'PASS')

    def test_no_source_denial(self):
        self.assertEqual(audit(self.fixture('no source separation'))['verdict'], 'PASS')

    def test_test_only(self):
        for path in ['tests/run.py', 'test_audio.py', 'audio_test.py']:
            with self.subTest(path=path):
                root = self.fixture(files={path: 'x.separate_stems()'})
                self.assertEqual(audit(root)['findings'][0]['severity'], 'MEDIUM')
                self.assertEqual(self.cli(root)[0], 0)
                self.assertEqual(self.cli(root, '--fail-on', 'MEDIUM')[0], 2)

    def test_fences(self):
        for fence in ['```', '~~~', '   ```', '  ~~~~']:
            self.assertEqual(phrases_in(fence + 'text\nseparates stems\n' + fence), set())
        self.assertEqual(phrases_in('`separates stems`'), {'SEPARATION'})
        self.assertEqual(phrases_in('SEPARATES-STEMS'), {'SEPARATION'})
        self.assertEqual(phrases_in("doesn't separate stems"), {'NOSEPARATION'})
        self.assertEqual(phrases_in('separates\n\nstems'), set())
        self.assertEqual(phrases_in('xseparates stemsx'), set())

    def test_docs_selection(self):
        root = self.fixture('hello', {'nested/docs/a.md': 'separates stems'})
        self.assertEqual(self.cli(root)[0], 2)
        root = self.fixture('hello', {'nested/a.md': 'separates stems'})
        self.assertEqual(self.cli(root)[0], 0)

    def test_exclusions(self):
        for folder in ['fixtures', 'docs', 'examples']:
            root = self.fixture(files={folder + '/app.py': 'x.separate_stems()'})
            self.assertEqual(self.cli(root)[0], 2)

    def test_split_modules(self):
        for files in [
            {'a.py': 'import demucs', 'b.py': 'demucs.separate()'},
            {'a.py': 'from spleeter.separator import Separator\ns = Separator()', 'b.py': 's.separate()'},
            {'a.py': 'from engine import separate_stems', 'b.py': 'separate_stems()'},
        ]:
            self.assertEqual(self.cli(self.fixture(files=files))[0], 2)

    def test_symlinks(self):
        root = self.fixture()
        outside = self.fixture(files={'app.py': 'x.separate_stems()'})
        (root / 'link.py').symlink_to(outside / 'app.py')
        (root / 'linked').symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.cli(root)[0], 2)

    def test_ignore_verbose(self):
        root = self.fixture(files={'src/app.py': 'x.separate_stems()'})
        self.assertEqual(self.cli(root, '--ignore', 'src', '--ignore', 'other')[0], 2)
        self.assertIn('src/app.py', self.cli(root, '--verbose')[1])
        self.assertEqual(self.cli(root, '--ignore', 'sr')[0], 0)

    def test_errors(self):
        self.assertEqual(self.cli('/nonexistent-path-claim-audit')[0], 1)
        self.assertEqual(self.cli('.', '--fail-on', 'BAD')[0], 1)
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                main([])
        self.assertEqual(cm.exception.code, 1)
        root = self.fixture()
        (root / 'app.py').write_bytes(b'\xff')
        self.assertEqual(self.cli(root)[0], 1)

    def test_version_and_module(self):
        result = subprocess.run([sys.executable, '-m', 'source_separation_claim_audit', '--version'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), '0.1.0')

    def test_self_audit(self):
        self.assertEqual(audit(Path(__file__).resolve().parents[1])['verdict'], 'PASS')

POSITIVE = {
    'demucs': 'import demucs\ndemucs.separate()',
    'demucs_alias': 'import demucs as d\nd.separate()',
    'demucs_from': 'from demucs import separate\nseparate()',
    'demucs_from_alias': 'from demucs import separate as s\ns()',
    'spleeter': 'from spleeter.separator import Separator\ns = Separator()\ns.separate()',
    'spleeter_alias': 'from spleeter.separator import Separator as S\ns: object = S()\ns.separate()',
    'spleeter_module': 'import spleeter.separator as sp\ns = sp.Separator()\ns.separate()',
    'spleeter_from_module': 'from spleeter import separator as sp\ns = sp.Separator()\ns.separate()',
    'spleeter_qualified': 'import spleeter.separator\ns = spleeter.separator.Separator()\ns.separate()',
    'demucs_shadow_exempt': 'import demucs\ndef separate(): pass\ndemucs.separate()',
    'spleeter_shadow_exempt': 'from spleeter.separator import Separator\ndef separate(): pass\ns = Separator()\ns.separate()',
}
for operation in ('separate_stems', 'separate_sources', 'isolate_vocals', 'extract_stems', 'split_stems', 'separate_audio', 'demix_audio'):
    POSITIVE[operation] = 'engine.' + operation + '()'
    POSITIVE[operation + '_from'] = 'from engine import ' + operation + '\n' + operation + '()'
    POSITIVE[operation + '_alias'] = 'from engine import ' + operation + ' as go\ngo()'

NEGATIVE = {
    'imports': 'import demucs, spleeter, openunmix, torchaudio',
    'load': 'librosa.load(x); soundfile.read(x); wave.open(x).readframes(1); torchaudio.load(x)',
    'capture': 'mic.listen(); mic.record(); sounddevice.rec(); stream.read()',
    'playback': 'sounddevice.play(x)',
    'recognition': 'model.transcribe(x); r.recognize_google(x); model.stt(x)',
    'tts': 'engine.say(x); model.synthesize(x)',
    'vad': 'vad.is_speech(x); model.get_speech_timestamps(x); Pipeline.from_pretrained("segmentation")',
    'keywords': 'pvporcupine.create(); Model().predict(x); x.detect_keyword()',
    'verification': 'model.verify_files(a,b); VoiceEncoder().embed_utterance(x); x.verify_speaker()',
    'diarization': 'Pipeline.from_pretrained("diarization"); x.diarize()',
    'noise': 'noisereduce.reduce_noise(x); df.enhance(x); x.suppress_noise(); x.remove_noise()',
    'fingerprint': 'acoustid.fingerprint_file(x); Dejavu().fingerprint_directory(x); x.fingerprint_audio()',
    'events': 'AudioTagging().inference(x); YAMNet(x); x.detect_sound_event()',
    'genre': 'pipeline("audio-classification")(x); classifier.predict(x)',
    'features': 'librosa.feature.chroma_stft(x); librosa.feature.mfcc(x); librosa.feature.spectral_centroid(x)',
    'hash': 'hashlib.md5(data); hashlib.sha256(data)',
    'filter': 'signal.sosfilt(x); x.equalize()',
    'mix': 'x.mix_tracks(); x.overlay(y)',
    'normalize': 'x.normalize(); librosa.util.normalize(x)',
    'lone_separator': 'from spleeter.separator import Separator\ns = Separator()',
    'unbound': 's.separate()',
    'wrong_constructor': 'from other import Separator\ns = Separator()\ns.separate()',
    'bare_constructor': 's = Separator()\ns.separate()',
    'cli': 'subprocess.run(["demucs", "x.wav"]); subprocess.run(["spleeter", "separate"])',
    'string': 'x = "demucs separate spleeter Separator separate_stems"',
    'reference': 'import demucs\ndemucs.separate',
    'syntax': 'import demucs\ndemucs.separate((',
    'wrong_demucs_import': 'import other as demucs\ndemucs.separate()',
    'nested_demucs_base': 'import demucs\ndemucs.other.separate()',
    'relative_demucs': 'from .demucs import separate\nseparate()',
}
for operation in ('separate_stems', 'separate_sources', 'isolate_vocals', 'extract_stems', 'split_stems', 'separate_audio', 'demix_audio'):
    NEGATIVE[operation + '_bare'] = operation + '()'
    NEGATIVE[operation + '_shadow'] = 'def ' + operation + '(): pass\nengine.' + operation + '()'
    NEGATIVE[operation + '_method_shadow'] = 'class X:\n def ' + operation + '(self): pass\nengine.' + operation + '()'
    NEGATIVE[operation + '_alias_shadow'] = 'from engine import ' + operation + ' as go\ndef go(): pass\ngo()'


def make_evidence_test(source, expected):
    def test(self):
        self.assertEqual(evidence(source), expected)
        result = audit(self.fixture(files={'app.py': source}))
        self.assertEqual(result['verdict'], 'PASS' if expected else 'FAIL')
    return test

for label, source in POSITIVE.items():
    setattr(AuditTests, 'test_evidence_' + label, make_evidence_test(source, True))
for label, source in NEGATIVE.items():
    setattr(AuditTests, 'test_not_evidence_' + label, make_evidence_test(source, False))

if __name__ == '__main__':
    unittest.main()
