"""
Node 5: Policy Excerpt Retrieval

Retrieves relevant sections from the warranty policy document.
"""

from app.vector_store import get_vector_store
from app.state import ClaimState, PolicyExcerpt

def retrieve_policy_excerpts(state: ClaimState) -> ClaimState:
    """
    Retrieve relevant excerpts from the warranty policy using semantic search (RAG).
    
    Args:
        state: Current workflow state with extracted fields
        
    Returns:
        Updated state with policy excerpts
    """
    if state.get("workflow_status") == "ERROR":
        return state
        
    extracted = state.get("extracted_fields", {})
    product_name = state.get("product_name") or extracted.get("product_name", "Unknown Product")
    issue_desc = extracted.get("issue_description", "general warranty inquiry")
    policy_file = state.get("policy_file")
    policy_id = state.get("policy_id")
    product_id = state.get("product_id")
    
    try:
        store = get_vector_store()
        store.ensure_indexed()

        # 1. Query for the specific issue
        issue_query = f"warranty coverage for {issue_desc} on {product_name}"
        issue_results = store.query(
            issue_query,
            n_results=3,
            policy_id=policy_id,
            policy_file=policy_file,
            product_id=product_id
        )
        for res in issue_results:
            res["_query"] = "issue"
        
        # 2. Query for general warranty terms (period, exclusions)
        terms_query = f"warranty period duration coverage exclusions for {product_name}"
        terms_results = store.query(
            terms_query,
            n_results=2,
            policy_id=policy_id,
            policy_file=policy_file,
            product_id=product_id
        )
        for res in terms_results:
            res["_query"] = "terms"
        
        # Combine and deduplicate
        all_results = issue_results + terms_results
        seen_content = set()
        excerpts = []
        
        for res in all_results:
            content = res["content"]
            if content in seen_content:
                continue
            seen_content.add(content)
            
            # Create PolicyExcerpt
            # Metadata has "source" and "chunk_index"
            meta = res["metadata"]
            section_name = f"Excerpt from {meta.get('source', 'Policy')}"
            
            excerpts.append(PolicyExcerpt(
                section_name=section_name,
                content=content,
                relevance=f"Semantic Match (Distance: {res['distance']:.3f})",
                policy_id=meta.get("policy_id", ""),
                policy_file=meta.get("policy_file", ""),
                chunk_index=meta.get("chunk_index", ""),
                distance=res.get("distance", 0),
                query=res.get("_query", "")
            ))
            
        # Ensure we found something
        if not excerpts:
            # Fallback to general query if nothing specific found
            general_results = store.query(
                f"warranty policy for {product_name}",
                n_results=3,
                policy_id=policy_id,
                policy_file=policy_file,
                product_id=product_id
            )
            for res in general_results:
                res["_query"] = "fallback"
            for res in general_results:
                meta = res.get("metadata", {})
                excerpts.append(PolicyExcerpt(
                    section_name="General Policy",
                    content=res["content"],
                    relevance="Fallback Retrieval",
                    policy_id=meta.get("policy_id", ""),
                    policy_file=meta.get("policy_file", ""),
                    chunk_index=meta.get("chunk_index", ""),
                    distance=res.get("distance", 0),
                    query=res.get("_query", "fallback")
                ))

        return {
            **state,
            "policy_excerpts": excerpts,
            "full_policy_text": None,
            "policy_retrieval": {
                "strategy": "chroma",
                "queries": [
                    {"name": "issue", "text": issue_query},
                    {"name": "terms", "text": terms_query}
                ],
                "filters": {
                    "policy_id": policy_id or "",
                    "policy_file": policy_file or "",
                    "product_id": product_id or ""
                },
                "results": [
                    {
                        "policy_id": exc.get("policy_id", ""),
                        "policy_file": exc.get("policy_file", ""),
                        "chunk_index": exc.get("chunk_index", ""),
                        "distance": exc.get("distance", 0),
                        "query": exc.get("query", ""),
                        "content_snippet": exc.get("content", "")[:200]
                    }
                    for exc in excerpts
                ]
            }
        }
        
    except Exception as e:
        return {
            **state,
            "policy_excerpts": [],
            "full_policy_text": None,
            "error_message": f"RAG Retrieval Error: {e}"
        }
