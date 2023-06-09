"""
Разработанный Адриелу Ванг от ДанСтат Консульти́рования
"""

import torch

# Single Layer Perceptron ARIMA
class ArimaSlp(PerceptronMain):
    def __init__(self, p, d, q, optimizer_function = Optimizers.sgd_optimizer, weight_decay = 0.0, add_bias = True):
        self.p = p
        self.d = d
        self.q = q
        super().__init__(
            layer_sizes=[p + q, 1],
            activation_function="linear",
            optimizer_function=optimizer_function,
            weight_decay=weight_decay,
            add_bias=add_bias
        )

    def fit(self, y, epochs, batch_size, learning_rate, momentum = 0, epoch_step=100):
        if not isinstance(y, torch.Tensor):
            y = torch.tensor(y, dtype=torch.float64)

        y_d = torch.diff(y, n=self.d) if self.d > 0 else y

        X_ar = torch.zeros((len(y_d) - self.p, self.p), dtype=torch.float64)
        for t in range(self.p, len(y_d)):
            X_ar[t - self.p] = y_d[t - self.p:t]

        ar_coeffs = WorkhorseFunctions.ols_estimator_torch(X_ar, y_d[self.p:].view(-1, 1)).view(-1, 1)

        residuals = y_d[self.p:] - X_ar.mm(ar_coeffs).view(-1)

        X_ma = torch.zeros((len(residuals) - self.q + 1, self.q), dtype=torch.float64)
        for t in range(self.q - 1, len(residuals)):
            X_ma[t - self.q + 1] = residuals[t - self.q + 1:t + 1]

        ma_coeffs = WorkhorseFunctions.ols_estimator_torch(X_ma, residuals[self.q - 1:].view(-1, 1)).view(-1, 1)  # Added .view(-1, 1)

        X = torch.cat((X_ar[:len(X_ma)], X_ma), dim=1)

        # Initialize AR and MA weights
        initial_weights = torch.cat((ar_coeffs, ma_coeffs), dim=0).t()
        self.weights[0] = initial_weights

        super().fit(X, y_d[self.p + self.q - 1:], epochs = epochs, batch_size = batch_size, learning_rate = learning_rate, momentum = momentum, epoch_step = epoch_step)

    def predict_next_period(self, y, horizon):
        if not isinstance(y, torch.Tensor):
            y = torch.tensor(y, dtype=torch.float64)

        y_d = torch.diff(y, n=self.d) if self.d > 0 else y
        predictions = []

        for _ in range(horizon):
            X_ar = y_d[-self.p:].view(1, -1)
            X_ma = y_d[-self.q:].view(1, -1)

            X = torch.cat((X_ar, X_ma), dim=1)
            y_next_d = super().predict(X).item()
            y_next = y_next_d + y[-1] if self.d > 0 else y_next_d

            predictions.append(y_next)
            y_d = torch.cat((y_d, torch.tensor([y_next_d], dtype=torch.float64).unsqueeze(0)), dim=0)
            y = torch.cat((y, torch.tensor([y_next], dtype=torch.float64).unsqueeze(0)), dim=0)

        return torch.tensor(predictions)

# Deep Instrumental Variable 
class DeepIv:
    def __init__(self, first_stage_layer_sizes, second_stage_layer_sizes, first_activation, second_activation, optimizer_function, add_bias = True):
        self.first_stage_network = PerceptronMain(layer_sizes=first_stage_layer_sizes, activation_function=first_activation, optimizer_function=optimizer_function, add_bias = add_bias)
        self.second_stage_network = PerceptronMain(layer_sizes=second_stage_layer_sizes, activation_function=second_activation, optimizer_function=optimizer_function, add_bias = add_bias)

    def fit(self, X, Z, y, epochs, batch_size, learning_rate, first_momentum = 0, second_momentum = 0, epoch_step = 100):
        # Fit the first-stage network using Z as input and X as output
        self.first_stage_network.fit(Z, X, epochs, batch_size, learning_rate, first_momentum, epoch_step = epoch_step)

        # Estimate the instrument variable
        estimated_IV = self.first_stage_network.predict(Z)

        # Fit the second-stage network using the estimated instrument variable and y
        self.second_stage_network.fit(estimated_IV, y, epochs, batch_size, learning_rate, second_momentum, epoch_step=epoch_step)

    def predict(self, X):
        # Estimate the instrument variable
        #estimated_IV = self.first_stage_network.predict(Z)

        # Predict the outcome using the estimated instrument variable
        return self.second_stage_network.predict(X)

# Vector Autoencoding Nonlinear Autoregression
class Vanar:
    def __init__(self, n_lags, n_variables, hidden_layer_sizes, n_components, autoencoder_wd = 0.0, forecast_wd = 0.0, add_bias = True, autoencoder_activ="linear", forecaster_activ="linear",
                 autoen_optim=Optimizers.sgd_optimizer, fore_optim=Optimizers.sgd_optimizer):
        self.n_lags = n_lags
        self.n_variables = n_variables
        self.autoencoder = PerceptronMain(
            layer_sizes=[n_variables * n_lags, n_components, n_variables * n_lags],
            activation_function=autoencoder_activ,
            optimizer_function=autoen_optim,
            weight_decay=autoencoder_wd,
            add_bias = add_bias
        )
        self.forecaster = PerceptronMain(
            layer_sizes=[n_lags] + hidden_layer_sizes + [1],
            activation_function=forecaster_activ,
            optimizer_function=fore_optim,
            weight_decay=forecast_wd,
            add_bias = add_bias
        )

    def initialize_forecaster_weights(self, X, y):
        beta_hat = WorkhorseFunctions.ols_estimator_torch(X, y)
        self.forecaster.weights[0].data = beta_hat.t()

    def fit(self, data, auto_epochs, fore_epochs, batch_size, learning_rate, first_momentum = 0, second_momentum=0, validation_split=0.2, epoch_step=None):
        # Prepare the input-output pairs
        X, y = WorkhorseFunctions.create_input_output_pairs(data, self.n_lags)
    
        # Split the data into training and validation sets
        n_validation = int(validation_split * X.shape[0])
        X_train, y_train = X[:-n_validation], y[:-n_validation]
        X_val, y_val = X[-n_validation:], y[-n_validation:]
    
        # Train the autoencoder
        self.autoencoder.fit(X_train, X_train, epochs=auto_epochs, batch_size=batch_size, learning_rate=learning_rate, 
                            momentum = first_momentum,
                            epoch_step=epoch_step)
    
        # Encode the input data
        X_train_encoded = self.autoencoder.predict(X_train)[:, :self.n_lags]
        X_val_encoded = self.autoencoder.predict(X_val)[:, :self.n_lags]
    
        # Change y_train shape
        y_train = y_train.view(-1, self.n_variables)
    
        # Initialize VANAR weights
        self.initialize_forecaster_weights(X_train_encoded, y_train)
    
        # Train the forecaster
        self.forecaster.fit(X_train_encoded, y_train, epochs=fore_epochs, batch_size=batch_size, learning_rate=learning_rate,
                            momentum = second_momentum,
                            epoch_step=epoch_step)

        self.X_encoded, self.y = torch.cat((X_train_encoded, X_val_encoded), dim=0), y

        # Compute validation MSE
        y_val_pred = self.forecaster.predict(X_val_encoded)
        mse_val = torch.mean((y_val_pred - y_val) ** 2)
        print("Validation MSE:", mse_val.item())

    def predict_next_period(self, data, horizon):
        predictions = []

        for _ in range(horizon):
            X, _ = WorkhorseFunctions.create_input_output_pairs(data, self.n_lags)
            X_encoded = self.autoencoder.predict(X)[:, :self.n_lags]
            y_next = self.forecaster.predict(X_encoded[-1].unsqueeze(0)).item()
            predictions.append(y_next)
            data = torch.cat((data, torch.tensor([y_next])), dim=0)

        return torch.tensor(predictions)

    def nonlinear_granger_causality(self, epochs, batch_size, learning_rate, momentum = 0, weight_decay = 0.0, activation_function="linear", exclude_variable=None):
        error_variance_full = self.compute_forecast_error_variance(self.X_encoded, self.y)

        gc_indices = []
        for i in range(self.n_lags):
            if i == exclude_variable:
                continue

            X_reduced_encoded = torch.cat((self.X_encoded[:, :i], self.X_encoded[:, i+1:]), dim=1)
        
            reduced_forecaster = PerceptronMain(
                layer_sizes=[self.n_lags - 1] + self.forecaster.layer_sizes[1:-1] + [1],
                activation_function=activation_function,
                optimizer_function=self.forecaster.optimizer_function,
                weight_decay=weight_decay,
                add_bias=self.forecaster.add_bias
            )

            # Fit the reduced forecaster
            reduced_forecaster.fit(X_reduced_encoded, 
                self.y, epochs=epochs, 
                batch_size=batch_size, 
                learning_rate=learning_rate,
                momentum = momentum)

            error_variance_reduced = self.compute_forecast_error_variance(X_reduced_encoded, self.y, reduced_forecaster)

            gc_index = 1 - error_variance_reduced / error_variance_full
            gc_indices.append(gc_index.item())

        return gc_indices

    def compute_forecast_error_variance(self, X_encoded, y, forecaster=None):
        if forecaster is None:
            forecaster = self.forecaster
        y_pred = forecaster.predict(X_encoded)
        return torch.mean((y_pred - y) ** 2)

    def granger_causality_p_values(self, gc_indices): 
        p_values = []
        dof = self.n_lags * self.n_variables
    
        for gc_index in gc_indices:
            LR = -2 * torch.log(torch.tensor(gc_index))
            p_value = 1 - self.chi2_cdf(LR, dof)
            p_values.append(p_value.item())
    
        return p_values

    # Temporary solution until PyTorchDistributionsExtended is finished
    def chi2_cdf(self, x, k):
        k = torch.tensor(k, dtype=torch.float64)  # Convert k to a tensor
        return torch.igamma(k / 2, x / 2)

class DeepGmm:
    def __init__(self, first_stage_layer_sizes, second_stage_layer_sizes, first_activation, second_activation, optimizer_function, add_bias=True):
        self.first_stage_network = PerceptronMain(layer_sizes=first_stage_layer_sizes, activation_function=first_activation, optimizer_function=optimizer_function, add_bias=add_bias)
        self.second_stage_network = PerceptronMain(layer_sizes=second_stage_layer_sizes, activation_function=second_activation, optimizer_function=optimizer_function, add_bias=add_bias)

    def gmm_loss(self, y_pred, y_true, weights):
        moment_conditions = y_true - y_pred

        # Compute the GMM loss
        gmm_loss = (moment_conditions.T * weights) @ moment_conditions

        return gmm_loss

    def fit(self, X, Z, y, epochs, batch_size, learning_rate, first_momentum = 0, second_momentum = 0, gmm_steps=1, regularize=False, regularization_param=1e-6, epoch_step=100):
        # Fit the first-stage network using Z as input and X as output
        self.first_stage_network.fit(Z, X, epochs, batch_size, learning_rate, first_momentum, epoch_step=epoch_step)

        # Estimate the instrument variable
        estimated_IV = self.first_stage_network.predict(Z)

        # Initialize GMM weights
        gmm_weights = torch.eye(y.shape[1]) / y.shape[1]

        for step in range(gmm_steps):
            # Fit the second-stage network using the estimated instrument variable and y
            self.second_stage_network.fit(estimated_IV, y, epochs, batch_size, learning_rate, second_momentum, epoch_step=epoch_step)

            # Predict the outcome using the estimated instrument variable
            y_pred = self.second_stage_network.predict(estimated_IV)

            # Calculate the moment conditions
            moment_conditions = y - y_pred

            # Update the GMM weights
            gmm_weights = self.update_gmm_weights(moment_conditions, regularize=regularize, regularization_param=regularization_param)

            # Calculate the GMM loss
            loss = self.gmm_loss(y_pred, y, gmm_weights)
            print(f"GMM step {step + 1}, loss: {loss.item()}")

    def update_gmm_weights(self, moment_conditions, regularize=False, regularization_param=1e-6):
        # Calculate the moment matrix
        moment_matrix = moment_conditions.T @ moment_conditions

        # Regularize the moment matrix if needed
        if regularize:
            moment_matrix += regularization_param * torch.eye(moment_matrix.shape[0])

        # Compute the inverse of the moment matrix
        inverse_moment_matrix = torch.inverse(moment_matrix)

        # Update the GMM weights
        new_weights = inverse_moment_matrix / torch.trace(inverse_moment_matrix)

        return new_weights

    def predict(self, X):
        # Predict the outcome using the estimated instrument variable
        return self.second_stage_network.predict(X)

