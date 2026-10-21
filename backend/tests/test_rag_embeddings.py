from app.services.rag_embeddings import cosine_similarity


def test_cosine_similarity_identical_vectors():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_similarity_orthogonal_vectors():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_invalid_vectors():
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([1.0], [1.0, 0.0]) == 0.0
