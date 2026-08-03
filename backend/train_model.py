import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import joblib

df = pd.read_csv("train_data.csv")
activity_encoder = LabelEncoder()
df["Activity_Encoded"] = activity_encoder.fit_transform(df["Activity"].str.lower())

FEATURES = ["T2M", "WS10M", "PRECTOTCORR", "CloudPct", "Activity_Encoded"]
X = df[FEATURES]

y = df["Suitability"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

model = RandomForestClassifier(n_estimators=100, random_state=42)
print("Starting Model Training...")
model.fit(X_train, y_train)
print("Training Complete.")

joblib.dump(model, "activity_suitability_model.pkl")
joblib.dump(activity_encoder, "activity_encoder.pkl")
print("Model (activity_suitability_model.pkl) and Encoder (activity_encoder.pkl)")
print(f"Model Accuracy on test data: {model.score(X_test, y_test)*100:.2f}%")
