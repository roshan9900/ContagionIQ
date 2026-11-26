from __future__ import annotations
from collections import deque
from typing import Any
import networkx as nx
from contracts.schema import SupplyEdgeRecord

class SupplyChainGraphEngine:
    def __init__(self,edges: list[SupplyEdgeRecord])->None:
        self.edges = edges
        self.graph: nx.DiGraph = self._build_graph(edges)
        
    @staticmethod
    def _build_graph(edges: list[SupplyEdgeRecord])->nx.DiGraph:
        graph = nx.DiGraph()
        for edge in edges:
            graph.add_edge(
                edge.source_id,
                edge.target_id,
                relationship=edge.relationship,
                dependency_pct=edge.dependency_pct,
                evidence_doc_id=edge.evidence_doc_id,
                evidence_quote=edge.evidence_quote,
                confidence=edge.confidence
            )
        return graph
    
    
    def traverse_exposure(
        self,
        seed_company_ids: list[str],
        max_hops: int=2
    )->list[dict[str,Any]]:
        results: list[dict[str,Any]] = []
        queue: deque[tuple[str,list[str],float,list[dict[str,Any]]]] = deque()
        
        for seed_id in seed_company_ids:
            if seed_id in self.graph:
                queue.append((seed_id,[seed_id],1.0,[]))
        while queue:
            current_id, path, cumulative_factor,evidence_trail = queue.popleft()
            current_hop = len(path)-1
            if current_hop>=max_hops:
                continue
            for neighbor_id in self.graph.successors(current_id):
                if neighbor_id in path:
                    continue
                edge_data = self.graph.get_edge_data(current_id,neighbor_id) or {}
                dep_pct = float(edge_data.get('dependency_pct',0.0))
                next_hop = current_hop+1
                next_path = path+[neighbor_id]
                next_factor = round(cumulative_factor*dep_pct,4)
                
                ev_entry = {
                    'from':current_id,
                    'to':neighbor_id,
                    'doc_id':edge_data.get('evidence_doc_id','UNKNOWN'),
                    'confidence':float(edge_data.get('confidence',0.0)),
                    'quote':edge_data.get('evidence_quote',""),
                }
                next_evidence = evidence_trail + [ev_entry]
                results.append(
                    {
                        "company_id": neighbor_id,
                        "hop": next_hop,
                        "path": " -> ".join(next_path),
                        "relationship": edge_data.get("relationship", "SUPPLIES_TO"),
                        "direct_dependency_pct": round(dep_pct * 100.0, 1),
                        "cumulative_pass_through": next_factor,
                        "evidence": next_evidence,
                    }
                )
                if next_hop < max_hops:
                    queue.append((neighbor_id, next_path, next_factor, next_evidence))
        return results