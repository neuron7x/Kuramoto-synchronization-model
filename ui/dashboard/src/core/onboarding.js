import { escapeHtml, serializeForScript } from './formatters.js';
import { t, getMessage } from '../i18n/index.js';

const DEFAULT_STORAGE_KEY = 'tp:onboarding:v1';
const FALLBACK_PROGRESS_TEMPLATE = 'Step {current} of {total}';

function normaliseSelectors(selectors) {
  if (!selectors) {
    return [];
  }
  const list = Array.isArray(selectors) ? selectors : [selectors];
  return list
    .map((selector) => (typeof selector === 'string' ? selector.trim() : ''))
    .filter(Boolean);
}

function buildDefaultSteps() {
  return [
    {
      id: 'navigation',
      title: t('onboarding.steps.navigation.title'),
      description: t('onboarding.steps.navigation.description'),
      selectors: ['[data-role="primary-nav"]'],
    },
    {
      id: 'workspace',
      title: t('onboarding.steps.workspace.title'),
      description: t('onboarding.steps.workspace.description'),
      selectors: ['#tp-main-content .tp-view__header', '.tp-view__header', '.tp-view'],
    },
    {
      id: 'insights',
      title: t('onboarding.steps.insights.title'),
      description: t('onboarding.steps.insights.description'),
      selectors: ['[data-role="overview-hero"]', '.tp-panels', '.tp-shell'],
    },
  ];
}

function normaliseSteps(steps, defaults) {
  const source = Array.isArray(steps) && steps.length > 0 ? steps : defaults;
  return source
    .map((step, index) => {
      if (!step || typeof step !== 'object') {
        return null;
      }
      const fallback = defaults.find((candidate) => candidate.id === step.id) || {};
      const selectors = normaliseSelectors(step.selectors ?? step.selector);
      const resolvedSelectors = selectors.length > 0 ? selectors : fallback.selectors || [];
      return {
        id: step.id || `step-${index + 1}`,
        title: step.title || fallback.title || '',
        description: step.description || fallback.description || '',
        selectors: resolvedSelectors,
      };
    })
    .filter((step) => step && step.title && step.description && step.selectors.length > 0);
}

function resolveTranslations() {
  const onboardingMessages = getMessage('onboarding') || {};
  const cta = onboardingMessages.cta || {};
  const progress = typeof onboardingMessages.progress === 'string'
    ? onboardingMessages.progress
    : FALLBACK_PROGRESS_TEMPLATE;

  return {
    heading: onboardingMessages.title || t('onboarding.title'),
    skip: cta.skip || t('onboarding.cta.skip'),
    next: cta.next || t('onboarding.cta.next'),
    finish: cta.finish || t('onboarding.cta.finish'),
    previous: cta.previous || t('onboarding.cta.previous'),
    progress,
  };
}

export function renderOnboarding(options = {}) {
  const { enabled = true, steps = [], storageKey = DEFAULT_STORAGE_KEY } = options || {};
  if (!enabled) {
    return { markup: '', script: '' };
  }

  const defaults = buildDefaultSteps();
  const resolvedSteps = normaliseSteps(steps, defaults);
  if (resolvedSteps.length === 0) {
    return { markup: '', script: '' };
  }

  const labels = resolveTranslations();
  const payload = resolvedSteps.map((step) => ({
    id: step.id,
    title: step.title,
    description: step.description,
    selectors: step.selectors,
  }));

  const markup = `
    <div
      class="tp-onboarding"
      data-role="onboarding"
      hidden
      aria-hidden="true"
      data-next-label="${escapeHtml(labels.next)}"
      data-finish-label="${escapeHtml(labels.finish)}"
      data-previous-label="${escapeHtml(labels.previous)}"
      data-progress-template="${escapeHtml(labels.progress)}"
      data-storage-key="${escapeHtml(storageKey || DEFAULT_STORAGE_KEY)}"
    >
      <section class="tp-onboarding__panel" role="dialog" aria-modal="false" aria-live="polite" data-role="onboarding-dialog">
        <header class="tp-onboarding__header">
          <p class="tp-onboarding__eyebrow">${escapeHtml(labels.heading)}</p>
          <h2 class="tp-onboarding__title" data-role="onboarding-title"></h2>
        </header>
        <p class="tp-onboarding__description" data-role="onboarding-description"></p>
        <footer class="tp-onboarding__footer">
          <div class="tp-onboarding__progress" data-role="onboarding-progress" aria-live="polite"></div>
          <div class="tp-onboarding__controls">
            <button type="button" class="tp-onboarding__control tp-onboarding__control--muted" data-action="onboarding-skip">${escapeHtml(
              labels.skip,
            )}</button>
            <div class="tp-onboarding__nav">
              <button type="button" class="tp-onboarding__control tp-onboarding__control--muted" data-action="onboarding-prev">${escapeHtml(
                labels.previous,
              )}</button>
              <button type="button" class="tp-onboarding__control tp-onboarding__control--primary" data-action="onboarding-next">${escapeHtml(
                labels.next,
              )}</button>
            </div>
          </div>
        </footer>
      </section>
      <script type="application/json" data-role="onboarding-steps">${serializeForScript(payload)}</script>
    </div>
  `;

  const script = `
    <script>
      (function () {
        if (typeof document === 'undefined') {
          return;
        }
        var root = document.querySelector('[data-role="onboarding"]');
        if (!root) {
          return;
        }
        var storageKey = root.getAttribute('data-storage-key') || '${DEFAULT_STORAGE_KEY}';
        var stepsNode = root.querySelector('script[data-role="onboarding-steps"]');
        var steps = [];
        if (stepsNode) {
          try {
            steps = JSON.parse(stepsNode.textContent || '[]') || [];
          } catch (error) {
            if (typeof console !== 'undefined' && console.warn) {
              console.warn('Failed to parse onboarding steps', error);
            }
            steps = [];
          }
        }
        if (!Array.isArray(steps) || steps.length === 0) {
          if (root.parentNode) {
            root.parentNode.removeChild(root);
          }
          return;
        }
        function readCookie(name) {
          if (typeof document === 'undefined' || !document.cookie) {
            return null;
          }
          var segments = document.cookie.split(';');
          for (var i = 0; i < segments.length; i += 1) {
            var segment = segments[i] ? segments[i].trim() : '';
            if (!segment) {
              continue;
            }
            if (segment.indexOf(name + '=') === 0) {
              var value = segment.slice(name.length + 1);
              try {
                return JSON.parse(decodeURIComponent(value)) || null;
              } catch (error) {
                return null;
              }
            }
          }
          return null;
        }

        var storedState = null;
        try {
          if (typeof window !== 'undefined' && window.localStorage) {
            var raw = window.localStorage.getItem(storageKey);
            if (raw) {
              storedState = JSON.parse(raw) || null;
            }
          }
        } catch (error) {
          storedState = null;
        }
        if (!storedState) {
          storedState = readCookie(storageKey);
        }
        if (storedState && storedState.completed) {
          if (root.parentNode) {
            root.parentNode.removeChild(root);
          }
          return;
        }
        var titleNode = root.querySelector('[data-role="onboarding-title"]');
        var descriptionNode = root.querySelector('[data-role="onboarding-description"]');
        var progressNode = root.querySelector('[data-role="onboarding-progress"]');
        var nextButton = root.querySelector('[data-action="onboarding-next"]');
        var prevButton = root.querySelector('[data-action="onboarding-prev"]');
        var skipButton = root.querySelector('[data-action="onboarding-skip"]');
        var dialog = root.querySelector('[data-role="onboarding-dialog"]');
        var nextLabel = root.getAttribute('data-next-label') || 'Next';
        var finishLabel = root.getAttribute('data-finish-label') || nextLabel;
        var previousLabel = root.getAttribute('data-previous-label') || 'Back';
        var progressTemplate = root.getAttribute('data-progress-template') || '';
        var activeTarget = null;
        var index = 0;

        function persistState(state) {
          try {
            if (typeof window !== 'undefined' && window.localStorage) {
              window.localStorage.setItem(storageKey, JSON.stringify(state));
            }
          } catch (error) {
            if (typeof console !== 'undefined' && console.debug) {
              console.debug('Unable to persist onboarding state', error);
            }
          }
          try {
            if (typeof document !== 'undefined') {
              document.cookie =
                storageKey + '=' + encodeURIComponent(JSON.stringify(state)) + ';path=/' + ';max-age=' + String(60 * 60 * 24 * 365) + ';SameSite=Lax';
            }
          } catch (cookieError) {
            if (typeof console !== 'undefined' && console.debug) {
              console.debug('Unable to persist onboarding cookie', cookieError);
            }
          }
        }

        function complete() {
          persistState({ completed: true, completedAt: new Date().toISOString() });
          if (activeTarget) {
            activeTarget.removeAttribute('data-onboarding-highlight');
            activeTarget = null;
          }
          root.setAttribute('aria-hidden', 'true');
          root.hidden = true;
        }

        function focusDialog() {
          if (!dialog || typeof dialog.focus !== 'function') {
            return;
          }
          dialog.setAttribute('tabindex', '-1');
          dialog.focus();
        }

        function formatProgress(current, total) {
          if (!progressTemplate) {
            return '';
          }
          return progressTemplate
            .replace(/\{current\}/gi, String(current))
            .replace(/\{total\}/gi, String(total));
        }

        function ensureVisible(target) {
          if (!target) {
            return;
          }
          try {
            if (typeof target.scrollIntoView === 'function') {
              target.scrollIntoView({ block: 'center', behavior: 'smooth' });
            }
          } catch (error) {
            try {
              target.scrollIntoView();
            } catch (scrollError) {
              if (typeof console !== 'undefined' && console.debug) {
                console.debug('Unable to scroll onboarding target into view', scrollError);
              }
            }
          }
        }

        function activateTarget(target) {
          if (activeTarget === target) {
            return;
          }
          if (activeTarget) {
            activeTarget.removeAttribute('data-onboarding-highlight');
          }
          activeTarget = target;
          if (activeTarget) {
            activeTarget.setAttribute('data-onboarding-highlight', 'true');
          }
        }

        function resolveTarget(step) {
          if (!step || !Array.isArray(step.selectors)) {
            return null;
          }
          for (var i = 0; i < step.selectors.length; i += 1) {
            var selector = step.selectors[i];
            if (!selector) {
              continue;
            }
            var node = document.querySelector(selector);
            if (node) {
              return node;
            }
          }
          return null;
        }

        function updateControls() {
          if (prevButton) {
            if (index <= 0) {
              prevButton.setAttribute('disabled', 'true');
              prevButton.classList.add('tp-onboarding__control--disabled');
            } else {
              prevButton.removeAttribute('disabled');
              prevButton.classList.remove('tp-onboarding__control--disabled');
            }
            prevButton.textContent = previousLabel;
          }
          if (nextButton) {
            var isLast = index >= steps.length - 1;
            nextButton.textContent = isLast ? finishLabel : nextLabel;
          }
          if (progressNode) {
            progressNode.textContent = formatProgress(index + 1, steps.length);
          }
        }

        function renderStep(stepIndex, direction) {
          if (stepIndex < 0 || stepIndex >= steps.length) {
            complete();
            return;
          }
          index = stepIndex;
          var step = steps[stepIndex];
          var target = resolveTarget(step);
          if (!target) {
            var nextIndex = direction && direction < 0 ? stepIndex - 1 : stepIndex + 1;
            if (nextIndex === stepIndex) {
              complete();
              return;
            }
            renderStep(nextIndex, direction);
            return;
          }
          if (titleNode) {
            titleNode.textContent = step.title || '';
          }
          if (descriptionNode) {
            descriptionNode.textContent = step.description || '';
          }
          root.hidden = false;
          root.setAttribute('aria-hidden', 'false');
          activateTarget(target);
          updateControls();
          ensureVisible(target);
          focusDialog();
        }

        function nextStep() {
          if (index >= steps.length - 1) {
            complete();
            return;
          }
          renderStep(index + 1, 1);
        }

        function prevStep() {
          if (index <= 0) {
            return;
          }
          renderStep(index - 1, -1);
        }

        function handleKeydown(event) {
          if (!event) {
            return;
          }
          var key = event.key || event.code;
          if (key === 'Escape' || key === 'Esc') {
            complete();
          }
          if ((key === 'ArrowRight' || key === 'Enter') && !event.shiftKey) {
            event.preventDefault();
            nextStep();
          }
          if (key === 'ArrowLeft') {
            event.preventDefault();
            prevStep();
          }
        }

        if (nextButton) {
          nextButton.addEventListener('click', function () {
            if (index >= steps.length - 1) {
              complete();
            } else {
              nextStep();
            }
          });
        }
        if (prevButton) {
          prevButton.addEventListener('click', function () {
            prevStep();
          });
        }
        if (skipButton) {
          skipButton.addEventListener('click', function () {
            complete();
          });
        }
        root.addEventListener('keydown', handleKeydown);
        window.addEventListener('resize', function () {
          if (!activeTarget) {
            return;
          }
          ensureVisible(activeTarget);
        });
        window.addEventListener('scroll', function () {
          if (!activeTarget) {
            return;
          }
          ensureVisible(activeTarget);
        }, { passive: true });

        renderStep(0, 1);
      })();
    </script>
  `;

  return { markup, script };
}
