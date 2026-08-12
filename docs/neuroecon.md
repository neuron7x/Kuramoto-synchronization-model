# Документація до модуля `AdvancedNeuroEconCore`

## Огляд реалізації
Модуль **NeuroEcon** у GeoSync представлений єдиним файлом [`core/neuro/advanced/neuroecon.py`](../core/neuro/advanced/neuroecon.py). Він містить реалізацію графового актор-критика `AdvancedNeuroEconCore`, який моделює прийняття рішень із дофаміновою модуляцією та контролем ризику. Додатково модуль експортує утилітарний дата-клас `DecisionOption` для безпечного перетворення сирих конфігурацій опцій.

На відміну від повноцінного Python-пакету з підмодулями, у репозиторії **немає** директорії `neuroecon/` із файлами `core.py`, `indicators.py`, `pivots.py` тощо. Документація стосується лише наявної реалізації `AdvancedNeuroEconCore` й допоміжних типів з цього файлу.

## Архітектура та залежності
- **Графовий енкодер**: `_NeuroGraphEncoder` виконує однокрокову агрегацію повідомлень на фіксованому маточному графі, створюючи приховані представлення стану.
- **Актор**: невелика `nn.Sequential` мережа, що перетворює значення стану на логіти політики.
- **Критик**: мережа, яка оцінює очікувану цінність наступного стану й використовується в обчисленні помилки темпоральної різниці.
- **Сховище Q-значень**: словник у памʼяті (`Dict[(state, action), value]`), що дозволяє поєднувати табличний Q-апдейт із нейромережевою апроксимацією.

> **Залежності**: для виконання необхідний `torch` (PyTorch). Якщо бібліотека недоступна, конструктор `AdvancedNeuroEconCore` підніме `ModuleNotFoundError` із поясненням.

## Ключові параметри конструктора
```python
AdvancedNeuroEconCore(
    hidden_dim: int = 64,
    gamma: float = 0.95,
    alpha: float = 0.1,
    dopamine_scale: float = 0.54,
    risk_tolerance: float = 0.48,
    uncertainty_reduction: float = 0.30,
    psychiatric_mod: float = 1.0,
    seed: int | None = 42,
    device: str | None = None,
    adjacency: Sequence[Sequence[float]] | None = None,
    temperature: float = 1.0,
)
```
- `hidden_dim`: розмір прихованого простору для енкодера, актора й критика.
- `gamma`: коефіцієнт дисконтування майбутніх нагород.
- `alpha`: швидкість навчання при оновленні Q-значень.
- `dopamine_scale`: масштабування модульованої TD-помилки.
- `risk_tolerance`, `uncertainty_reduction`, `psychiatric_mod`: параметри, що впливають на зважування винагороди/ризику/вартості.
- `adjacency`: користувацька матриця суміжності для графового енкодера (за замовчуванням використовується збалансований 4-вузловий граф).
- `temperature`: температура софтмакс-політики; повинна бути > 0.

## Публічні методи
- `DecisionOption.from_mapping(mapping)`: перетворює словник (наприклад, `{"reward": 1.0}`) на імунний до відсутніх ключів `DecisionOption`.
- `AdvancedNeuroEconCore.evaluate_option(option)`: повертає субʼєктивну цінність опції з урахуванням ризику та невизначеності.
- `AdvancedNeuroEconCore.evaluate_options(options)`: батчова версія, що повертає `torch.Tensor` на пристрої моделі.
- `AdvancedNeuroEconCore.policy_distribution(options, temperature=None)`: генерує `torch.distributions.Categorical` разом із оціненими значеннями опцій.
- `AdvancedNeuroEconCore.simulate_decision(options, temperature=None, deterministic=False)`: вибір дії за політикою з можливістю детермінованого режиму.
- `AdvancedNeuroEconCore.temporal_difference_error(state, action, reward, next_state, next_action)`: сирий TD-розрахунок.
- `AdvancedNeuroEconCore.update_Q(...)`: застосовує TD-помилку, модульовану дофаміном, і повертає величину оновлення.
- `AdvancedNeuroEconCore.train_on_scenario(states, actions, rewards)`: проходить послідовність епізодів і повертає історію модульованих TD-помилок.
- `AdvancedNeuroEconCore.get_q_value(state, action)`: читає поточну оцінку Q для стану/дії.

## Приклад використання
```python
from core.neuro.advanced.neuroecon import AdvancedNeuroEconCore, DecisionOption

core = AdvancedNeuroEconCore(hidden_dim=32, gamma=0.9, alpha=0.05)
options = [
    DecisionOption(reward=1.0, risk=0.2, cost=0.1),
    {"reward": 0.4, "risk": 0.05, "cost": 0.0},  # автоматично конвертується
]

distribution, values = core.policy_distribution(options)
choice, subjective_value = core.simulate_decision(options)

states = [0.0, 0.4, 0.6]
actions = [choice, choice, choice]
rewards = [0.2, 0.1]
updates = core.train_on_scenario(states, actions, rewards)
```

## Тестування та валідація
На момент написання документації модуль покривається модульними тестами загальної батареї `pytest`, що перевіряє:
- правильність побудови графового енкодера;
- валідацію вхідних параметрів (температура, форма ознак, довжина сценарію);
- очікувану поведінку при відсутності PyTorch (викид `ModuleNotFoundError`).

Тестові сценарії знаходяться у загальному каталозі `tests/` та запускаються командою `pytest core/neuro/advanced/test_neuroecon.py` (якщо доступні).

## Обмеження та примітки
- Модуль не включає в себе генерацію індикаторів, пошук дивергенцій чи CLI-інструменти; ці функції мають реалізовуватися у вищих шарах GeoSync.
- При роботі на CPU з великими графами швидкодія залежить від розміру матриці суміжності та параметра `hidden_dim`.
- Для детермінованого відтворення встановлюйте `seed` під час ініціалізації та використовуйте фіксовану матрицю суміжності.

## Подальші кроки
Інтегруючи `AdvancedNeuroEconCore` в нові пайплайни, рекомендується:
1. Нормувати вхідні стани до діапазону `[0, 1]` або `[-1, 1]` для стабільності навчання.
2. Логувати історію `updates` із `train_on_scenario` для моніторингу зходимості.
3. Виносити генерацію `DecisionOption` у спеціалізовані адаптери, які перетворюють доменні метрики (прибуток/ризик/вартість) на числові атрибути.
