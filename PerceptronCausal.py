from collections import defaultdict
import torch
import pandas as pd
import itertools
from typing import Union
import matplotlib.pyplot as plt
import plotly.graph_objects as go

class CausalDAG:
    def __init__(self):
        self.graph = defaultdict(list)

    def add_edge(self, u, v):
        self.graph[u].append(v)

    def show_edges(self):
        for node in self.graph:
            for neighbor in self.graph[node]:
                print(f"{node} -> {neighbor}")
                
#import torch
import pandas as pd
import itertools
from typing import Union
import matplotlib.pyplot as plt
import plotly.graph_objects as go

class CausalInference:
    def __init__(self, data: pd.DataFrame, treatment: str, outcome: str, graph: Union[CausalDAG, str] = None):
        self.data = data
        self.treatment = treatment
        self.outcome = outcome
        self.graph = graph

    def estimate_effect(self, method_name="mdm", hidden_layer_sizes = [10], activation_function = "linear", optimizer_function = Optimizers.sgd_optimizer, momentum = 0.0, weight_decay = 0.0):
        if not hasattr(self, "estimand"):
            self.identify_effect()
    
        X = torch.tensor(self.data.drop(columns=[self.treatment, self.outcome]).values).float()
        y = torch.tensor(self.data[self.outcome].values).float()
        treatment = torch.tensor(self.data[self.treatment].values).float()

        if method_name == "mdm":
            mdm = MahalanobisMatcher(perceptron=True)
            mdm.fit(X, y, treatment, hidden_layer_sizes = hidden_layer_sizes, activation_function = activation_function, optimizer_function = optimizer_function, momentum = momentum, weight_decay = weight_decay)
            self.estimate = mdm.predict(X, treatment)
        else:
            raise ValueError(f"Unsupported estimation method: {method_name}")

        return self.estimate

    def backdoor_criterion(self, Z):
        """
        Check if the set of variables Z satisfies the backdoor criterion.
        """
        # Check if there are any common causes of treatment and outcome that are not in Z
        for node in self.graph.graph[self.treatment]:
            if node not in Z and node in self.graph.graph[self.outcome]:
                return False

        # Check if there are any common causes of treatment and any variable in Z that are not in Z
        for node in Z:
            for common_cause in self.graph.graph[self.treatment]:
                if common_cause not in Z and common_cause in self.graph.graph[node]:
                    return False

        return True

    def identify_effect(self):
        if self.graph is None:
            # Implement your own graph discovery algorithm
            pass

        # Get all variables except treatment and outcome
        variables = [v for v in self.data.columns if v not in [self.treatment, self.outcome]]

        # Try all possible combinations of variables as potential covariate sets
        for i in range(len(variables) + 1):
            for covariate_set in itertools.combinations(variables, i):
                if self.backdoor_criterion(set(covariate_set)):
                    self.estimand = set(covariate_set)
                    return

        raise ValueError("No valid set of covariates found that satisfies the backdoor criterion.")

    def refute_effect(self, method_name="random_common_cause", **kwargs):
        if not hasattr(self, "estimate"):
            self.estimate_effect()

        if method_name == "random_common_cause":
            return self.random_common_cause_refutation()
        else:
            raise ValueError(f"Unsupported refutation method: {method_name}")

    def random_common_cause_refutation(self, method_name="mdm", hidden_layer_sizes = [10], activation_function = "linear", optimizer_function = Optimizers.sgd_optimizer, momentum = 0.0, weight_decay = 0.0):
        random_common_cause = torch.randn(len(self.data))
        data_with_random_common_cause = self.data.copy()
        data_with_random_common_cause["random_common_cause"] = random_common_cause

        ci_with_random_common_cause = CausalInference(
            data=data_with_random_common_cause,
            treatment=self.treatment,
            outcome=self.outcome,
            graph=self.graph
        )
        ci_with_random_common_cause.identify_effect()
        ate_estimate_with_random_common_cause = ci_with_random_common_cause.estimate_effect(method_name=method_name,
                                                hidden_layer_sizes=hidden_layer_sizes, 
                                                activation_function = activation_function,
                                                optimizer_function = optimizer_function,
                                                momentum = momentum,
                                                weight_decay=weight_decay)
        self.refutation_estimate = ate_estimate_with_random_common_cause

        return {
            "original_estimate": self.estimate,
            "estimate_with_random_common_cause": ate_estimate_with_random_common_cause
        }

    def summary(self):
        if not hasattr(self, "estimate"):
            raise ValueError(f"Perform estimates first")

        if not hasattr(self, "refutation_estimate"):
            raise ValueError(f"Perform refutation first")

        print("Causal Estimate")
        print("--------------")
        print(self.estimate)
        print("Mean estimate:")
        print(torch.mean(self.estimate))
        print("\nRefutation Results")
        print("-------------------")
        print(self.refutation_estimate)
        print("Mean refutation:")
        print(torch.mean(self.refutation_estimate))

    def plot_estimates(self, use_plotly=True, plot_type="average"):
        if not hasattr(self, "estimate"):
            self.estimate_effect()

        estimate_with_random_common_cause = self.refutation_estimate
        original_estimate = self.estimate
        #estimate_with_random_common_cause = refutation_result["estimate_with_random_common_cause"]

        if plot_type == "average":
            original_estimate_mean = torch.mean(original_estimate)
            estimate_with_random_common_cause_mean = torch.mean(estimate_with_random_common_cause)

            if use_plotly:
                fig = go.Figure()
                fig.add_trace(go.Bar(x=["Original Estimate", "Estimate with Random Common Cause"], y=[original_estimate_mean, estimate_with_random_common_cause_mean], text=[original_estimate_mean, estimate_with_random_common_cause_mean], textposition='auto'))
                fig.update_layout(title="Average Treatment Effect Estimates")
                fig.show()
            else:
                plt.bar(["Original Estimate", "Estimate with Random Common Cause"], [original_estimate_mean, estimate_with_random_common_cause_mean])
                plt.title("Average Treatment Effect Estimates")
                plt.show()
        elif plot_type == "side_by_side":
            num_observations = len(original_estimate)
            index = torch.arange(num_observations)
            bar_width = 0.35

            if use_plotly:
                fig = go.Figure()
                fig.add_trace(go.Bar(x=index, y=original_estimate, width=bar_width, name="Original Estimate"))
                fig.add_trace(go.Bar(x=index+bar_width, y=estimate_with_random_common_cause, width=bar_width, name="Estimate with Random Common Cause"))
                fig.update_layout(title="Treatment Effect Estimates for Each Observation", xaxis_title="Observations", yaxis_title="Estimated Average Treatment Effect")
                fig.show()
            else:
                plt.figure(figsize=(12, 6))
                plt.bar(index, original_estimate, bar_width, label="Original Estimate")
                plt.bar(index + bar_width, estimate_with_random_common_cause, bar_width, label="Estimate with Random Common Cause")
                plt.xlabel("Observations")
                plt.ylabel("Estimated Average Treatment Effect")
                plt.title("Comparison of EATE with and without Random Common Cause")
                plt.xticks(index + bar_width / 2, range(1, num_observations + 1))
                plt.legend()
                plt.show()
        else:
            raise ValueError("Invalid plot_type value. Choose 'average' or 'side_by_side'.")
            
class MahalanobisMatcher:
    def __init__(self, n_neighbors=1, perceptron=False):
        self.n_neighbors = n_neighbors
        self.perceptron = perceptron

    def fit(self, X, y, treatment, hidden_layer_sizes, activation_function, optimizer_function, momentum, weight_decay):
        self.X = X
        self.y = y
        self.treatment = treatment

        if self.perceptron:
            self.model = PerceptronMain([X.shape[1]] + hidden_layer_sizes + [1], activation_function = activation_function, optimizer_function = optimizer_function, weight_decay = weight_decay)
            self.model.fit(X, y, epochs=1000, 
            batch_size=32, 
            learning_rate=0.0001, 
            momentum = momentum,
            epoch_step=100,)

    def predict(self, X, treatment_values):
        # Compute the Mahalanobis distance
        cov_matrix = torch.tensor(WorkhorseFunctions.torch_cov(self.X, rowvar=False))
        inv_cov_matrix = torch.inverse(cov_matrix)
        mahalanobis_distances = self.pairwise_mahalanobis_distances(X, self.X, inv_cov_matrix)

        # Find the indices of the closest n_neighbors for each instance in X
        _, neighbor_indices = torch.topk(-mahalanobis_distances, self.n_neighbors, dim=1)

        # Compute the average treatment effect for each instance in X using the matched neighbors
        treatment_effects = []
        for i in range(X.shape[0]):
            treatment_values_neighbors = self.treatment[neighbor_indices[i]]
            treated_indices = neighbor_indices[i][treatment_values_neighbors == treatment_values[i]]
            control_indices = neighbor_indices[i][treatment_values_neighbors != treatment_values[i]]

            if self.perceptron:
                treated_outcomes = self.model.predict(self.X[treated_indices])
                control_outcomes = self.model.predict(self.X[control_indices])
            else:
                treated_outcomes = self.y[treated_indices]
                control_outcomes = self.y[control_indices]

            treatment_effect = (torch.sum(treated_outcomes) - torch.sum(control_outcomes)) / (treated_indices.numel() + control_indices.numel() + 1e-8)
            treatment_effects.append(treatment_effect)

        return torch.tensor(treatment_effects)

    def pairwise_mahalanobis_distances(self, X, Y, inv_cov_matrix):
        # Subtract the mean from the data points
        X_centered = X - torch.mean(X, axis=0)
        Y_centered = Y - torch.mean(Y, axis=0)

        # Compute the squared Mahalanobis distance
        X_transformed = X_centered @ inv_cov_matrix
        Y_transformed = Y_centered @ inv_cov_matrix
        squared_mahalanobis_distances = torch.cdist(X_transformed, Y_transformed, p=2)**2

        return squared_mahalanobis_distances
