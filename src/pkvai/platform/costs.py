"""What a case costs on a model, from the contract's token counts and the platform's prices."""


def per_case(model: str, tokens: dict, models: dict) -> float:
    m = models[model]
    if model == "classical":
        return m["compute_eur_per_case"]
    return (tokens["in"] * m["in_per_mtok_eur"] + tokens["out"] * m["out_per_mtok_eur"]) / 1e6
