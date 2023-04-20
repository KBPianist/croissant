import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import mean_squared_error, f1_score, make_scorer
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error
import numpy as np
import sys
import os

zid = os.path.basename(sys.modules[__name__].__file__).split('.')[0]

class ATMClassifierRegressor:
    def __init__(self, train_data_path, test_data_path, debug=False):
        self.train_data_path = train_data_path
        self.test_data_path = test_data_path
        self.debug = debug
        self.train_df = None
        self.test_df = None
        self.X_train = None
        self.X_test = None
        self.y_train = None
        self.y_test = None
        self.label_encoder = LabelEncoder()

    def load_data(self):
        """Load train and test data."""

        self.train_df = pd.read_csv(self.train_data_path, sep='\t')
        self.test_df = pd.read_csv(self.test_data_path, sep='\t')
        print('shape of train:', self.train_df.shape, ', shape of test:', self.test_df.shape)

    def feature_engineering(self):
        """Prepare features for training."""

        excluded_features = ['revenue', 'rating']
        categorical_features = ['ATM_Zone', 'ATM_Placement', 'ATM_TYPE', 'ATM_Location_TYPE',
                                'ATM_looks', 'ATM_Attached_to', 'Day_Type']
        numeric_features = [col for col in self.train_df.columns if col not in excluded_features + categorical_features]

        self.train_df['class_label'] = self.label_encoder.fit_transform(self.train_df['rating'])

        X = self.train_df.drop(columns=['revenue', 'rating'])
        y = self.train_df[['revenue', 'class_label']]

        self.X_train, self.X_val, self.y_train, self.y_val = train_test_split(X, y, test_size=0.2, random_state=42)
        self.X_test = self.test_df.drop(columns=['revenue', 'rating'])
        self.y_test = self.test_df[['revenue', 'rating']]

        self.preprocessor = ColumnTransformer(
            transformers=[
                ('num', StandardScaler(), numeric_features),
                ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_features)])

        # Fit the preprocessor on the training data and transform the training, validation, and test sets
        self.X_train = self.preprocessor.fit_transform(self.X_train)
        self.X_val = self.preprocessor.transform(self.X_val)
        self.X_test = self.preprocessor.transform(self.X_test)

    def select_and_train_models(self):
        """Select, train and evaluate models using GridSearchCV and Pipelines."""

        # Scoring functions for GridSearchCV
        mse_scorer = make_scorer(mean_squared_error, greater_is_better=False)
        f1_scorer = make_scorer(f1_score, greater_is_better=True, average='weighted')

        # Regression model
        regression_pipeline = Pipeline([
            ('regressor', RandomForestRegressor())
        ])

        if self.debug:
            regression_param_grid = {
                'regressor__n_estimators': [50, 100, 200],
                'regressor__max_depth': [None, 10, 20],
                'regressor__min_samples_split': [2, 5, 10]
            }
        else:
            regression_param_grid = {
                'regressor__n_estimators': [200],
                'regressor__max_depth': [None],
                'regressor__min_samples_split': [10]
            }

        regression_grid_search = GridSearchCV(regression_pipeline, param_grid=regression_param_grid, scoring=mse_scorer, cv=5, n_jobs=-1, pre_dispatch='2*n_jobs')
        regression_grid_search.fit(self.X_train, self.y_train['revenue'])
        self.regression_model = regression_grid_search.best_estimator_
        # print(regression_grid_search.best_params_)

        # Evaluate validation set for regression model
        y_val_pred = self.regression_model.predict(self.X_val)
        pearson_val = r2_score(self.y_val['revenue'], y_val_pred) ** 0.5

        # Evaluate test set for regression model
        y_test_pred_revenue = self.regression_model.predict(self.X_test)
        pearson_test = r2_score(self.y_test['revenue'], y_test_pred_revenue) ** 0.5

        # Print the evaluation metrics
        print(f"Validation Pearson correlation coefficient : {pearson_val}")
        print(f"Test Pearson correlation coefficient : {pearson_test}")

        # Classification model
        classification_pipeline = Pipeline([
            ('classifier', RandomForestClassifier())
        ])

        if self.debug:
            classification_param_grid = {
                'classifier__n_estimators': [50, 100, 200],
                'classifier__max_depth': [None, 10, 20],
                'classifier__min_samples_split': [2, 5, 10]
            }
        else:
            classification_param_grid = {
                'classifier__n_estimators': [200],
                'classifier__max_depth': [None],
                'classifier__min_samples_split': [10]
            }

        classification_grid_search = GridSearchCV(classification_pipeline, param_grid=classification_param_grid, scoring=f1_scorer, cv=5, n_jobs=-1)
        classification_grid_search.fit(self.X_train, self.y_train['class_label'])
        self.classification_model = classification_grid_search.best_estimator_
        # print(classification_grid_search.best_params_)

        # Evaluate validation set for classification model
        y_val_class_pred = self.classification_model.predict(self.X_val)
        f1_val = f1_score(self.y_val['class_label'], y_val_class_pred, average='weighted')
        print(f"Validation F1 Score: {f1_val}")

        # Evaluate test set for classification model
        y_test_pred_class_label = self.classification_model.predict(self.X_test)
        y_test_pred_rating = self.label_encoder.inverse_transform(y_test_pred_class_label)
        f1_test = f1_score(self.y_test['rating'], y_test_pred_rating, average='weighted')
        print(f"Test F1 Score: {f1_test}")

    def predict_and_save_results(self):
        """Predict and save results for test data."""

        predicted_revenue = self.regression_model.predict(self.X_test)
        predicted_class_labels = self.classification_model.predict(self.X_test)
        predicted_ratings = self.label_encoder.inverse_transform(predicted_class_labels)

        # Save predicted revenue to a separate file
        revenue_output_df = pd.DataFrame({'predicted_revenue': predicted_revenue})
        revenue_output_df.to_csv('{}.PART1.output.csv'.format(zid), index=False)

        # Save predicted ratings to a separate file
        rating_output_df = pd.DataFrame({'predicted_rating': predicted_ratings})
        rating_output_df.to_csv('{}.PART2.output.csv'.format(zid), index=False)



    def run(self):
        """Run the entire process."""
        
        import time
        start_time = time.time()
        try:
            self.load_data()
            self.feature_engineering()
            self.select_and_train_models()
            self.predict_and_save_results()
        except Exception as e:
            print(f"An error occurred during execution: {e}")
        print(f"Total execution time: {time.time() - start_time} seconds")

if __name__ == '__main__':
    classifier_regressor = ATMClassifierRegressor(train_data_path=sys.argv[1],
                                                  test_data_path=sys.argv[2],
                                                  debug=False)  # Set to False for submission mode
    classifier_regressor.run()

