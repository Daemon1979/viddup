# Встановлення viddup

Ця інструкція розрахована на Python 3.12 і FreeBSD-подібний деплой, де важкі
Python-бібліотеки краще ставити системними пакетами, а потім використовувати їх
з virtualenv.

## 1. Встановити системні пакети

На FreeBSD треба встановити і конкретний Python, і `python3` meta-port/wrapper.
Саме wrapper дає `/usr/local/bin/python3`; він не завжди ставиться разом з
`python312`.

Модуль SQLite для Python теж окремий пакет. Без нього `dupfind` падає з
`ModuleNotFoundError: No module named '_sqlite3'`.

Базовий набір пакетів:

```sh
pkg install python312 python3 py312-sqlite3 ffmpeg sqlite3 \
  py312-imageio py312-numpy py312-pyyaml py312-scipy py312-tqdm \
  py312-pytest
```

Потрібен хоча б один KNN backend. Рекомендований і дефолтний варіант -
`hnswlib`. Став через packages або ports, залежно від того, що є на машині:

```sh
pkg install py312-hnswlib py312-annoy py312-pynndescent
```

Якщо потрібного пакета нема, постав backend з ports або через `pip` вже після
створення venv.

Опціональні backend-и для benchmark/debug:

```sh
pkg install py312-scikit-learn py312-faiss
```

`sklearn` і `faiss` корисні як точний baseline, але для повного radius search
на великих базах вони набагато повільніші за `hnswlib`.

## 2. Створити venv

Використовуй `--system-site-packages`, щоб venv бачив системні Python-модулі:

```sh
cd /path/to/viddup
/usr/local/bin/python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -U pip
```

## 3. Встановити viddup

Для звичайного використання:

```sh
python -m pip install .
```

Для розробки і локальних тестів:

```sh
python -m pip install -e ".[test]"
```

Якщо `hnswlib` не був встановлений системно, рекомендований fallback -
поставити його з upstream-проєкту всередині активованого venv:

```sh
git clone https://github.com/nmslib/hnswlib.git
cd hnswlib
python -m pip install .
```

Сторінка проєкту: <https://github.com/nmslib/hnswlib>

## 4. Перевірити встановлення

```sh
python -c "import sqlite3, _sqlite3; print(sqlite3.sqlite_version)"
python -c "from viddup.knn import available_backends; print(available_backends())"
dupfind --help
python -m pytest -q
```

У списку KNN має бути хоча б один backend. Найкраще, якщо там є `hnswlib`.

## 5. Опціональний wrapper

Після створення venv і встановлення `viddup` можна користуватись wrapper-ом і
не активувати venv вручну кожного разу:

```sh
./dupfind.sh --help
./dupfind.sh --db videos.db --search
```

За замовчуванням wrapper використовує `.venv` поруч зі скриптом. Якщо треба
вказати інший venv:

```sh
VIDDUP_VENV=/path/to/venv ./dupfind.sh --help
```

## 6. Типові команди

Створити або оновити базу:

```sh
dupfind --db videos.db --dir /PATH/video
```

Під час імпорту директорії за замовчуванням використовується до чотирьох
паралельних процесів хешування. Записи у SQLite при цьому залишаються
послідовними й атомарними. Кількість процесів можна змінити:

```sh
dupfind --db videos.db --dir /PATH/video --numjobs 6
```

Для HDD або мережевого сховища варто зменшити значення, якщо паралельне читання
знижує загальну швидкість.

Пропустити директорії під час скану:

```sh
dupfind --db videos.db --dir /PATH/video \
  --exclude-dir /PATH/video/skip-this-dir \
  --exclude-dir /PATH/other-media
```

Пошук дублікатів:

```sh
dupfind --db videos.db --search
```

Стандартний пошук використовує довжину fingerprint 12 і radius 3. На великих
реальних базах це дало хороший баланс між корисними збігами та хибними
результатами:

```sh
dupfind --db videos.db --search
```

Для пошуку коротших або менш схожих фрагментів можна ввімкнути чутливіший режим:

```sh
dupfind --db videos.db --search --indexlength 11
dupfind --db videos.db --search --indexlength 10
```

Коротший fingerprint підвищує чутливість і кількість хибних результатів.
Зменшення `--radius` нижче стандартного 3 робить пошук суворішим, але може
приховати копії після зміни FPS, монтажу або кодування.

KNN-кандидатів можна додатково перевірити за нормалізованими профілями
покадрової яскравості, які вже збережені в базі:

```sh
dupfind --db videos.db --search --verify-brightness
```

Стандартний мінімальний коефіцієнт кореляції - `0.70`. Його можна змінити:

```sh
dupfind --db videos.db --search --verify-brightness \
  --brightness-correlation 0.80
```

На цьому етапі відео повторно не декодуються. Нормалізація дозволяє пережити
зміну загальної яскравості, кодека, роздільної здатності та HDR/SDR. Вищий
поріг прибирає більше хибних збігів, але може відкинути сильніше змонтовані або
інакше підготовлені копії.

### Конфігураційний файл

`viddup` читає TOML-конфіг спочатку з `~/.config/viddup/viddup.conf`, потім з
`./viddup.conf`, а після цього зі шляху, переданого через `--config`. Пізніший
файл і параметри CLI мають вищий пріоритет. Приклад є у
`viddup.conf.example`.

Секція `[import]` містить параметри імпорту, а `[search]` - параметри пошуку.
Масиви `exclude_dirs` у них незалежні. Неактивні секції ігноруються, тому один
конфіг може безпечно містити налаштування для всіх режимів.

Вибрати вбудований або власний профіль пошуку:

```sh
dupfind --db videos.db --search --profile precise
```

Примусово вибрати KNN backend:

```sh
dupfind --db videos.db --search --knnlib hnswlib
dupfind --db videos.db --search --knnlib annoy
dupfind --db videos.db --search --knnlib pynndescent
```

Пошук з ігноруванням уже захешованих шляхів:

```sh
dupfind --db videos.db --search --search-exclude-dir /PATH/video/skip-this-dir
```

Подивитись вміст бази:

```sh
dupfind --db videos.db --list-db-dirs
dupfind --db videos.db --list-db-files --list-db-path /PATH/video/skip-this-dir
```

Dry-run видалення шляху з бази:

```sh
dupfind --db videos.db --delete-db-path /PATH/video/skip-this-dir
```

Реально видалити цей шлях з бази:

```sh
dupfind --db videos.db --delete-db-path /PATH/video/skip-this-dir --delete
```

Вичистити з бази записи про файли, яких уже нема на диску:

```sh
dupfind --db videos.db --purge
dupfind --db videos.db --purge --delete
```

## 7. Примітки про backend-и

Дефолтний порядок вибору:

1. `hnswlib`
2. `cyflann`
3. `annoy`
4. `sklearn`
5. `faiss`
6. `pynndescent`

Практична рекомендація:

- Для нормальної роботи використовуй `hnswlib`. На реальній базі він був
  найшвидшим і після нормалізації radius збігся з точним baseline.
- `annoy` або `pynndescent` можна використовувати як альтернативу, якщо
  `hnswlib` недоступний.
- `sklearn` і `faiss` краще лишити для debug або benchmark. Їх точний radius
  mode дуже повільний на великих базах.

## 8. Типові проблеми

Нема SQLite-модуля:

```text
ModuleNotFoundError: No module named '_sqlite3'
```

Постав `py312-sqlite3`, пересоздай або реактивуй venv і перевір:

```sh
python -c "import sqlite3, _sqlite3"
```

Нема KNN backend-а:

```text
Please install at least one KNN library
```

По можливості спочатку постав `hnswlib`. Якщо не виходить - постав `annoy` або
`pynndescent`.

Повільні exact backend-и:

`sklearn` і `faiss` можуть бути дуже повільні, бо використовуються як точний
radius baseline. Це нормально; для звичайного запуску краще `hnswlib`.
