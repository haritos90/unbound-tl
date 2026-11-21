from gen3tl.data.pokedextexts import dataset_dir

DATASET = dataset_dir("unbound-2.1.1.1")

def trainer(trainer_id=1, class_id=57):
    return {"id": trainer_id, "class_id": class_id, "ai_flags": 1, "party_flags": 0}

def member(species=19, level=10, spread=0, moves=None):
    return {"index": 0, "species": species, "level": level, "iv": spread, "moves": moves}

def uniform(value, speed=None):
    result = [value] * 6
    if speed is not None:
        result[3] = speed
    return result
