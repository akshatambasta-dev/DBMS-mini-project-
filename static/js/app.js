document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.flash').forEach((element) => {
    window.setTimeout(() => {
      element.classList.add('flash-dismissed');
      window.setTimeout(() => element.remove(), 250);
    }, 6500);
  });

  document.querySelectorAll('[data-toggle-password]').forEach((button) => {
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.togglePassword);
      if (!input) return;
      const reveal = input.type === 'password';
      input.type = reveal ? 'text' : 'password';
      button.textContent = reveal ? 'Hide' : 'Show';
      button.setAttribute('aria-label', reveal ? 'Hide password' : 'Show password');
    });
  });

  const addButton = document.querySelector('[data-add-question]');
  const questionList = document.getElementById('questions');
  const questionCount = document.getElementById('question-count');

  const refreshQuestionCount = () => {
    if (!questionList || !questionCount) return;
    const count = questionList.querySelectorAll('.question-row').length;
    questionCount.textContent = count === 1 ? '1 question' : count + ' questions';
    if (addButton) {
      addButton.disabled = count >= 30;
      addButton.textContent = count >= 30 ? 'Maximum questions reached' : '＋ Add a question';
    }
  };

  if (addButton && questionList) {
    addButton.addEventListener('click', () => {
      const count = questionList.querySelectorAll('.question-row').length;
      if (count >= 30) return;

      const row = document.createElement('div');
      row.className = 'question-row';

      const input = document.createElement('input');
      input.name = 'question_text[]';
      input.maxLength = 300;
      input.required = true;
      input.placeholder = 'Write your question';
      input.setAttribute('aria-label', 'Question ' + (count + 1));

      const select = document.createElement('select');
      select.name = 'question_kind[]';
      select.setAttribute('aria-label', 'Answer type');
      [['rating', '1–5 rating'], ['text', 'Written answer']].forEach(([value, label]) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        select.appendChild(option);
      });

      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'remove-question';
      remove.textContent = 'Remove';
      remove.setAttribute('aria-label', 'Remove question ' + (count + 1));
      remove.addEventListener('click', () => {
        row.remove();
        refreshQuestionCount();
      });

      row.append(input, select, remove);
      questionList.appendChild(row);
      input.focus();
      refreshQuestionCount();
    });

    refreshQuestionCount();
  }
});