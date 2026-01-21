from app.nodes.retrieve_policy import retrieve_policy_excerpts


def test_retrieval():
    print("Testing RAG retrieval node...")

    # Mock state
    state = {
        "extracted_fields": {"issue_description": "device fell in water and stopped working"},
        "product_name": "ProStyle 3000"
    }

    # Run retrieval
    result = retrieve_policy_excerpts(state)

    excerpts = result.get("policy_excerpts", [])
    print(f"\nRetrieved {len(excerpts)} excerpts for 'water damage' on 'ProStyle 3000':")

    for i, exc in enumerate(excerpts):
        print(f"\nExcerpt {i + 1} ({exc['relevance']}):")
        print(f"Section: {exc['section_name']}")
        print("-" * 20)
        content = exc.get("content", "")
        print(content[:200] + "..." if len(content) > 200 else content)

    if len(excerpts) > 0:
        print("\nOK: Retrieval successful.")
    else:
        print("\nWARN: No excerpts retrieved.")


if __name__ == "__main__":
    test_retrieval()
