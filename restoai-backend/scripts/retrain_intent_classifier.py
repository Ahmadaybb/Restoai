"""Retrain the intent classifier on a comprehensive synthetic dataset."""
import hashlib
import json
from pathlib import Path

import joblib
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

print("sklearn version:", sklearn.__version__)

training_data = [
    # ORDER - English
    ("I want to order 2 hummus", "order"),
    ("order 1 falafel wrap please", "order"),
    ("Can I get a mixed grill plate", "order"),
    ("give me 3 shawarma", "order"),
    ("I would like 1 kibbeh", "order"),
    ("add fattoush to my cart", "order"),
    ("let me get 2 portions of tabbouleh", "order"),
    ("one large shawarma plate please", "order"),
    ("I will have the combo meal", "order"),
    ("add 1 tabbouleh to my order", "order"),
    ("put 2 kibbeh in my order", "order"),
    ("I want the veggie platter", "order"),
    ("can I order the family meal", "order"),
    ("place an order for hummus and pita", "order"),
    ("I need 4 falafel sandwiches", "order"),
    ("get me a shawarma and a drink", "order"),
    ("order: 1 kibbeh, no onions", "order"),
    ("give me 1 portion of kibbeh nayye", "order"),
    ("I would like the mixed grill for 2", "order"),
    ("I would like the combo meal please", "order"),
    ("Can I get a large mixed grill plate please", "order"),
    ("I want to order 2 hummus and 1 fattoush", "order"),
    ("2 hummus plates please", "order"),
    ("bring me the shish tawook", "order"),
    ("I will take 3 falafel and 1 tabbouleh", "order"),

    # ORDER - Arabizi
    ("bidi 3 shawarma w 2 falafel", "order"),
    ("bidi shawarma min fadlak", "order"),
    ("3tini 2 hummus", "order"),
    ("bidi 1 kibeh wa salata", "order"),
    ("3tini combo meal", "order"),
    ("bidi order shawarma plate", "order"),
    ("khalini akhod 2 falafel", "order"),
    ("3tini 3 shawarma w rice", "order"),
    ("biddi kibbeh min fadlak", "order"),
    ("bidi 1 tabbouleh w 2 shawarma", "order"),
    ("bidi 2 falafel sandwich", "order"),
    ("3tini 1 hummus w khobez", "order"),

    # ORDER - Arabic
    ("ممكن اطلب 2 حمص و سلطة", "order"),
    ("اعطني شاورما من فضلك", "order"),
    ("بدي اطلب فلافل", "order"),
    ("اطلب لي واحد كبة", "order"),
    ("ممكن تعطيني 3 شاورما", "order"),
    ("بدي اطلب وجبة", "order"),

    # RESERVATION - English
    ("I want to book a table for 4 at 7pm", "reservation"),
    ("can I make a reservation for Saturday night", "reservation"),
    ("reserve a table for 2 people", "reservation"),
    ("book me a spot for Friday dinner", "reservation"),
    ("I would like to make a reservation", "reservation"),
    ("can we book a table for tomorrow", "reservation"),
    ("reservation for 6 people please", "reservation"),
    ("I need a table for tonight at 8", "reservation"),
    ("book a table for my anniversary dinner", "reservation"),
    ("can you reserve a spot for 3", "reservation"),
    ("make a reservation for Sunday lunch", "reservation"),
    ("table for 2 this evening", "reservation"),
    ("reserve a table for next Friday", "reservation"),

    # QUERY - English (menu and restaurant questions)
    ("what is in the fattoush salad", "query"),
    ("is the hummus vegan", "query"),
    ("what are the ingredients in the mixed grill", "query"),
    ("do you have anything spicy", "query"),
    ("what is the price of the shawarma plate", "query"),
    ("is the restaurant open now", "query"),
    ("what time do you close", "query"),
    ("do you have vegetarian options", "query"),
    ("is the mixed grill halal", "query"),
    ("what does the fattoush contain", "query"),
    ("how much does the hummus cost", "query"),
    ("are there any gluten free options", "query"),
    ("what comes with the combo meal", "query"),
    ("do you deliver to downtown", "query"),
    ("what are your opening hours", "query"),
    ("is the kibbeh made with lamb", "query"),
    ("how many calories in the shawarma", "query"),
    ("what is in the tabbouleh", "query"),
    ("does the falafel have dairy", "query"),
    ("what sides come with the mixed grill", "query"),
    ("is the restaurant open on weekends", "query"),
    ("what are the ingredients in the fattoush salad", "query"),
    ("how spicy is the harissa", "query"),
    ("do you have a kids menu", "query"),
    ("what is included in the combo meal", "query"),

    # STATUS
    ("where is my order", "status"),
    ("how long will my delivery take", "status"),
    ("has my order been confirmed", "status"),
    ("when will my food arrive", "status"),
    ("is my order ready", "status"),
    ("what is the status of my order", "status"),
    ("track my delivery please", "status"),
    ("my order is late", "status"),
    ("how much longer for my delivery", "status"),
    ("did you receive my order", "status"),
    ("check my order status", "status"),
    ("I placed an order 30 minutes ago, where is it", "status"),
    ("can you check if my order was received", "status"),

    # IMAGE
    ("send me a picture of the menu", "image"),
    ("can you show me a photo of the mixed grill", "image"),
    ("show me what the shawarma looks like", "image"),
    ("do you have pictures of the food", "image"),
    ("send a photo of the fattoush", "image"),
    ("can I see an image of the hummus", "image"),
    ("what does the kibbeh look like", "image"),
    ("show me the menu with pictures", "image"),
    ("I want to see a photo before I order", "image"),
    ("send me the menu image", "image"),
    ("can you show me a photo of the falafel", "image"),
    ("I want to see what the tabbouleh looks like", "image"),
]

X = [t[0] for t in training_data]
y = [t[1] for t in training_data]

pipe = Pipeline([
    ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=15000)),
    ("clf", LinearSVC(C=1.0, max_iter=5000)),
])
pipe.fit(X, y)

# Evaluate on eval slice
eval_path = Path("tests/golden/intent/eval_slice.jsonl")
records = [
    json.loads(line)
    for line in eval_path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]
y_true = [r["intent"] for r in records]
y_pred_raw = [pipe.predict([r["text"]])[0] for r in records]

classes = sorted(set(y_true))
f1_scores = []
for cls in classes:
    tp = sum(t == cls and p == cls for t, p in zip(y_true, y_pred_raw))
    fp = sum(t != cls and p == cls for t, p in zip(y_true, y_pred_raw))
    fn = sum(t == cls and p != cls for t, p in zip(y_true, y_pred_raw))
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    f1_scores.append(f1)
    print(f"  {cls}: F1={f1:.3f}")

macro = sum(f1_scores) / len(f1_scores)
print(f"Macro F1 (raw predict): {macro:.4f}")

if macro < 0.93:
    print("WARNING: macro F1 below 0.93 — check training data coverage")
    wrong = [(r["text"], r["intent"], p) for r, p in zip(records, y_pred_raw) if r["intent"] != p]
    for text, expected, got in wrong:
        print(f"  WRONG: {text!r} expected={expected} got={got}")
else:
    print("OK: macro F1 >= 0.93")
    out = Path("data/intent_classifier.joblib")
    joblib.dump(pipe, out)
    md5 = hashlib.md5(out.read_bytes()).hexdigest()  # noqa: S324
    print(f"Saved to {out} (MD5: {md5})")
