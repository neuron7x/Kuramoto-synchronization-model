/**
 * Enhanced Onboarding Module
 * Supports role-based personalization and progress tracking
 */

import { escapeHtml, serializeForScript } from './formatters.js';
import { t, getMessage } from '../i18n/index.js';

const DEFAULT_STORAGE_KEY = 'tp:onboarding:v2';
const FALLBACK_PROGRESS_TEMPLATE = 'Step {current} of {total}';

/**
 * Role-based step definitions
 */
const ROLE_STEPS = {
  trader: [
    {
      id: 'portfolio',
      title: 'Portfolio Overview',
      description: 'Monitor your positions and P&L in real-time',
      selectors: ['[data-route="overview"]'],
      condition: () => true,
    },
    {
      id: 'orders',
      title: 'Order Management',
      description: 'Place and manage your trading orders',
      selectors: ['[data-route="orders"]'],
      condition: () => true,
    },
    {
      id: 'risk',
      title: 'Risk Controls',
      description: 'Set up risk limits and alerts',
      selectors: ['[data-route="monitoring"]'],
      condition: () => true,
    },
  ],
  analyst: [
    {
      id: 'monitoring',
      title: 'Market Monitoring',
      description: 'Track market conditions and anomalies',
      selectors: ['[data-route="monitoring"]'],
      condition: () => true,
    },
    {
      id: 'analytics',
      title: 'Analytics Tools',
      description: 'Use charts and indicators for analysis',
      selectors: ['[data-route="pnl"]'],
      condition: () => true,
    },
    {
      id: 'signals',
      title: 'Trading Signals',
      description: 'Review generated trading signals',
      selectors: ['[data-route="signals"]'],
      condition: () => true,
    },
  ],
  community: [
    {
      id: 'community',
      title: 'Community Hub',
      description: 'Connect with other traders and share insights',
      selectors: ['[data-route="community"]'],
      condition: () => true,
    },
    {
      id: 'events',
      title: 'Events Calendar',
      description: 'Stay updated on trading events and webinars',
      selectors: ['[data-role="events-tab"]'],
      condition: () => true,
    },
    {
      id: 'champions',
      title: 'Top Performers',
      description: 'Learn from champion traders',
      selectors: ['[data-role="champions-tab"]'],
      condition: () => true,
    },
  ],
  admin: [
    {
      id: 'dashboard',
      title: 'Admin Dashboard',
      description: 'Overview of system status and users',
      selectors: ['[data-route="overview"]'],
      condition: () => true,
    },
    {
      id: 'monitoring',
      title: 'System Monitoring',
      description: 'Monitor system health and performance',
      selectors: ['[data-route="monitoring"]'],
      condition: () => true,
    },
    {
      id: 'users',
      title: 'User Management',
      description: 'Manage user accounts and permissions',
      selectors: ['[data-role="user-management"]'],
      condition: () => true,
    },
  ],
};

/**
 * Get steps for a specific role
 * @param {string} role - User role
 * @param {Object} context - Context for condition evaluation
 * @returns {Array} - Filtered steps
 */
function getStepsForRole(role = 'trader', context = {}) {
  const roleSteps = ROLE_STEPS[role] || ROLE_STEPS.trader;
  return roleSteps.filter((step) => {
    if (typeof step.condition === 'function') {
      try {
        return step.condition(context);
      } catch (error) {
        console.warn('Error evaluating step condition:', error);
        return true;
      }
    }
    return true;
  });
}

/**
 * Load progress from local storage
 * @param {string} storageKey - Storage key
 * @returns {Object|null} - Progress object or null
 */
export function loadProgress(storageKey) {
  if (typeof window === 'undefined' || !window.localStorage) {
    return null;
  }

  try {
    const stored = window.localStorage.getItem(storageKey);
    if (!stored) {
      return null;
    }

    const data = JSON.parse(stored);
    if (data && typeof data === 'object') {
      return data;
    }
  } catch (error) {
    console.warn('Failed to load onboarding progress:', error);
  }

  return null;
}

/**
 * Save progress to local storage
 * @param {string} storageKey - Storage key
 * @param {Object} progress - Progress object
 */
export function saveProgress(storageKey, progress) {
  if (typeof window === 'undefined' || !window.localStorage) {
    return;
  }

  try {
    window.localStorage.setItem(storageKey, JSON.stringify(progress));
  } catch (error) {
    console.warn('Failed to save onboarding progress:', error);
  }
}

/**
 * Sync progress with backend
 * @param {string} userId - User ID
 * @param {Object} progress - Progress object
 * @param {Function} syncFn - Sync function (optional)
 * @returns {Promise<boolean>}
 */
export async function syncProgressToBackend(userId, progress, syncFn) {
  if (!userId) {
    return false;
  }

  if (typeof syncFn === 'function') {
    try {
      await syncFn(userId, progress);
      return true;
    } catch (error) {
      console.warn('Failed to sync onboarding progress:', error);
      return false;
    }
  }

  // Fallback to fetch if no sync function provided
  try {
    const response = await fetch(`/api/onboarding/progress/${userId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(progress),
    });
    return response.ok;
  } catch (error) {
    console.warn('Failed to sync onboarding progress:', error);
    return false;
  }
}

/**
 * Render enhanced onboarding with role support
 * @param {Object} options - Options
 * @returns {Object} - Markup and script
 */
export function renderEnhancedOnboarding(options = {}) {
  const {
    enabled = true,
    role = 'trader',
    userId = null,
    context = {},
    storageKey = DEFAULT_STORAGE_KEY,
    showSkip = true,
  } = options;

  if (!enabled) {
    return { markup: '', script: '' };
  }

  const steps = getStepsForRole(role, context);
  if (steps.length === 0) {
    return { markup: '', script: '' };
  }

  const labels = {
    heading: t('onboarding.title'),
    skip: t('onboarding.cta.skip'),
    next: t('onboarding.cta.next'),
    finish: t('onboarding.cta.finish'),
    previous: t('onboarding.cta.previous'),
    progress: getMessage('onboarding.progress') || FALLBACK_PROGRESS_TEMPLATE,
  };

  const payload = steps.map((step) => ({
    id: step.id,
    title: step.title,
    description: step.description,
    selectors: step.selectors,
  }));

  const config = {
    steps: payload,
    labels,
    role,
    userId,
    storageKey,
    showSkip,
  };

  const markup = `
    <div
      class="tp-onboarding tp-onboarding--enhanced"
      data-role="onboarding-enhanced"
      hidden
      role="dialog"
      aria-modal="true"
      aria-labelledby="tp-onboarding-title"
    >
      <div class="tp-onboarding__overlay"></div>
      <div class="tp-onboarding__panel">
        <div class="tp-onboarding__header">
          <h2 id="tp-onboarding-title" class="tp-onboarding__heading">${escapeHtml(labels.heading)}</h2>
          ${showSkip ? `<button type="button" class="tp-onboarding__skip" data-action="skip-onboarding" aria-label="${escapeHtml(labels.skip)}">${escapeHtml(labels.skip)}</button>` : ''}
        </div>
        <div class="tp-onboarding__body">
          <div class="tp-onboarding__step">
            <h3 class="tp-onboarding__step-title"></h3>
            <p class="tp-onboarding__step-description"></p>
          </div>
        </div>
        <div class="tp-onboarding__footer">
          <div class="tp-onboarding__progress" aria-live="polite"></div>
          <div class="tp-onboarding__actions">
            <button type="button" class="tp-onboarding__button tp-onboarding__button--secondary" data-action="previous-step">${escapeHtml(labels.previous)}</button>
            <button type="button" class="tp-onboarding__button tp-onboarding__button--primary" data-action="next-step">${escapeHtml(labels.next)}</button>
          </div>
        </div>
      </div>
      <div class="tp-onboarding__spotlight"></div>
    </div>
  `;

  const script = `
    <script type="application/json" data-role="onboarding-config">${serializeForScript(config)}</script>
    <script>
      (function() {
        if (typeof document === 'undefined') return;

        const container = document.querySelector('[data-role="onboarding-enhanced"]');
        if (!container) return;

        const configNode = document.querySelector('[data-role="onboarding-config"]');
        if (!configNode) return;

        const config = JSON.parse(configNode.textContent || '{}');
        const { steps, labels, role, userId, storageKey, showSkip } = config;
        
        let currentStepIndex = 0;
        let completed = false;

        // Load saved progress
        const savedProgress = loadProgress();
        if (savedProgress && savedProgress.role === role) {
          currentStepIndex = savedProgress.currentStep || 0;
          completed = savedProgress.completed || false;
        }

        // Don't show if already completed
        if (completed) {
          return;
        }

        function loadProgress() {
          try {
            const stored = window.localStorage.getItem(storageKey);
            return stored ? JSON.parse(stored) : null;
          } catch (error) {
            return null;
          }
        }

        function saveProgress(data) {
          try {
            window.localStorage.setItem(storageKey, JSON.stringify(data));
          } catch (error) {
            console.warn('Failed to save progress:', error);
          }
        }

        async function syncProgress(data) {
          if (!userId) return;
          try {
            await fetch(\`/api/onboarding/progress/\${userId}\`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(data),
            });
          } catch (error) {
            console.warn('Failed to sync progress:', error);
          }
        }

        function showStep(index) {
          if (index < 0 || index >= steps.length) {
            return;
          }

          currentStepIndex = index;
          const step = steps[index];

          // Update content
          const titleEl = container.querySelector('.tp-onboarding__step-title');
          const descEl = container.querySelector('.tp-onboarding__step-description');
          const progressEl = container.querySelector('.tp-onboarding__progress');
          const prevBtn = container.querySelector('[data-action="previous-step"]');
          const nextBtn = container.querySelector('[data-action="next-step"]');

          if (titleEl) titleEl.textContent = step.title;
          if (descEl) descEl.textContent = step.description;
          
          if (progressEl) {
            const progressText = labels.progress
              .replace(/{current}/gi, String(index + 1))
              .replace(/{total}/gi, String(steps.length));
            progressEl.textContent = progressText;
          }

          // Update buttons
          if (prevBtn) {
            prevBtn.disabled = index === 0;
          }
          
          if (nextBtn) {
            nextBtn.textContent = index === steps.length - 1 ? labels.finish : labels.next;
          }

          // Highlight element
          highlightElement(step.selectors);

          // Save progress
          const progress = {
            role,
            currentStep: index,
            completed: false,
            timestamp: Date.now(),
          };
          saveProgress(progress);
          syncProgress(progress);
        }

        function highlightElement(selectors) {
          // Find first matching element
          let target = null;
          for (const selector of selectors) {
            target = document.querySelector(selector);
            if (target) break;
          }

          const spotlight = container.querySelector('.tp-onboarding__spotlight');
          if (!spotlight) return;

          if (target) {
            const rect = target.getBoundingClientRect();
            spotlight.style.cssText = \`
              left: \${rect.left}px;
              top: \${rect.top}px;
              width: \${rect.width}px;
              height: \${rect.height}px;
              display: block;
            \`;
          } else {
            spotlight.style.display = 'none';
          }
        }

        function complete() {
          completed = true;
          const progress = {
            role,
            currentStep: steps.length,
            completed: true,
            timestamp: Date.now(),
          };
          saveProgress(progress);
          syncProgress(progress);

          // Dispatch complete event
          if (typeof window.CustomEvent === 'function') {
            window.dispatchEvent(new CustomEvent('tp:onboarding-complete', { detail: { role } }));
          }

          close();
        }

        function skip() {
          const progress = {
            role,
            currentStep: currentStepIndex,
            completed: false,
            skipped: true,
            timestamp: Date.now(),
          };
          saveProgress(progress);
          syncProgress(progress);

          // Dispatch skip event
          if (typeof window.CustomEvent === 'function') {
            window.dispatchEvent(new CustomEvent('tp:onboarding-skip', { detail: { role } }));
          }

          close();
        }

        function close() {
          container.hidden = true;
          container.setAttribute('aria-hidden', 'true');
        }

        function open() {
          container.hidden = false;
          container.removeAttribute('aria-hidden');
          showStep(currentStepIndex);
        }

        // Event handlers
        container.addEventListener('click', (event) => {
          const target = event.target;

          if (target.matches('[data-action="next-step"]')) {
            if (currentStepIndex === steps.length - 1) {
              complete();
            } else {
              showStep(currentStepIndex + 1);
            }
          }

          if (target.matches('[data-action="previous-step"]')) {
            showStep(currentStepIndex - 1);
          }

          if (target.matches('[data-action="skip-onboarding"]') || target.closest('.tp-onboarding__overlay')) {
            skip();
          }
        });

        // Keyboard navigation
        container.addEventListener('keydown', (event) => {
          if (event.key === 'Escape') {
            skip();
          }
        });

        // Auto-open on page load
        setTimeout(() => {
          open();
        }, 1000);
      })();
    </script>
  `;

  return { markup, script };
}
