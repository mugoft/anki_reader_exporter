
class Note:
    def __init__(self, note_id, mod, question, answer):
        self._note_id = note_id
        self._mod = mod
        self._question = question
        self._answer = answer

    def get_note_id(self):
        return self._note_id

    def get_mod(self):
        return self._mod

    def get_question(self):
        return self._question

    def get_answer(self):
        return self._answer

    def __str__(self):
        return "note_id=" + str(self._note_id) + " mod=" + str(self._mod) + " question=" + self._question + " answer=" + self._answer