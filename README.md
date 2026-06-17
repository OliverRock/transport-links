# Connectivity take home

Submission for the connectivity take home.

### Repo outline

`run_q1.py`, `run_q2.py` and `run_q3.py` contain code to demonstrate my solutions.

`petrochem.py` contains shared code for the three questions, this inlcudes reading data, the main data models and the actual business logic to answers I gave.

`/tests/` some basic tests written by claude

`/research/` contains some of my notes and research I did while thinking about the problem. Including: a glossary, some notes, screenshots and a lit review written by claude. The lit review is not really relevent to submission but I found it interesting to read to get myself in the right frame of mind to think about the problem.

I used `uv` to manage the environment. The model itself is stdlib only, the only dependency is matplotlib (in `requirements.txt`) for the Q2/Q3 plots. Set up with `uv venv && uv pip install -r requirements.txt`, then run the demos with `uv run run_q1.py` (or `run_q2.py`, `run_q3.py`).


### Contirbutions with AI

I used Claude for research and for writting code. This is my work as I directed to code writting, chose the structure of the solution and reviewed the AI generated work to make sure I agreed with the results. I have written this README without any assistance from Claude, everything in this doc is my own words.


## Answers

### Q1 - Domain modeling

The data gives use three physical things to model: piplines, facilities and units. The primary goal of this exercie is to model the real world and understand how materials flow around that system. I choose to model this as a graph. There are clear paralelles between nodes and edges. The nodes are the units, this where things happen to the materials, usually converted from one form to another. The edges are connections between units, which can be backed by a transport link. A facility is a geographically close grouping of units, it does not really tell use what is happening.

**Units:**

I am taking the definition of unit as given in the assignment without any change. It is a sub-asset in a facility which actually does the work. In the given data there are: ports, crude distillation, stream crackers. But complete models would need many more types of unit.

Unit features: Location, facility, type.

Other features which might be important in future models: Electical grid draw, life span, environmental concerns/efficiancy, name plate capacity.

```
class Unit:
    id: str
    facility_id: str # Location data is stored under the facility
    name: str
    unit_type: str
```


**Transport link and edges:**

In my model, transport links between two units are the edges on the graph. In the given data we have pipelines (crude, naphtha, ethylene). But this could also be shipping lane, rail, road or river.

In this model we have assumed that any gaps in the geo data of a pipeline can be interpolated. That they can be bidirectional (this is true of some pipelines, but not all). And I have assumed that any unit within a given distance of a pipeline can use it.

In this model each edge can only carry one type material. This works for pipelines where this is usually the case, but this might start to break down in cases where ships can transport mulitple types of material. I do not think this is an issue and infact might be a benefit. For example a naviagable river might have boats for two types of freight but not for a third, this could be cleanly expressed by using edges.

There is a danger of using unit to unit edges. Which is that the actual pipline information is split between multiple edges. If the pipeline has important constraints, it might be easier to model as a node. This is a point of contention and ulimatly I am not decided on which is a better approach. Shipping lanes feel more like edges but pipelines do not.


```
class Edge:
    commodity: str
    mode: str
    from_unit: Optional[str]
    to_unit: Optional[str]
    confidence: float
    note: str
```


**Facilities:**

In this model facilties do not provide that much important informaiton and are thus sidelined compared to units. 

The important features in this model are the units and location. In future models it might be important to model capacity, storage facilites, throughput, ownership and other infrastucture built there.

In the current set up the facilities are relativly simple. Each facility has one type of unit (expect ports with import and export units). They would become more important in future work if there was more informaiton and more complexity. For example, facilities with multiple types of units would be important to to model through put for the entire facility. Or if part of a facility goes down you would be able to model the redirected routes without the entire facility being offline.



### Q2 - Partial data

The data provided for this excerise was missing important transport links.

This was easily identifieable by looking for facilities which were not close to a pipeline. In reality no one would have an active facility without transport to get materials in and products out.

To address this I applied a few different heuristics to try to fill in the gaps.

Firstly, I allowed any facility within 5km to connect to a pipeline. When researching pipelines, I read that companies could build their own connections. This is an assuption which should be checked further, for example, does every pipeline allow this, is there a maximum length of connections, are there other reason to block this (eg passing thru a built up area).

The second approach I used was to allow transport between ports. Initially I thought this helps to see the shape of the map, but I actually think this was a mistake. I think that there should be a cost for short distance shipping lanes because I assume that you do not want to be loading and unloading ocean going vessals regularly.

Thirdly, I used a nearest neighbour approach to infer river transport.  This is too simplistic to be useful and it shows errors in the infered graph but this is only due to a lack of information. If it was possible to make a topological map which included rail links, roads, and navigable rivers, you could quite easily alter this approach to look for which is the nearest/cheapest route that a material can travel.

An important part of this is the pipelines in the data are observed, so I trust them. But the sea lanes and barges I have invented, so they should not be trusted in the same way. To handle this every edge carries a confidence score. The inferred edges get a deliberatly low confidence, with sea lanes scored higher than barges. The barges are lowest because I have no river data at all, so they are the most of a guess. I think this confidence score could easily be extended as more data is added.

On the barge distance cap, the 300km limit is really a stand in for navigability, I am using distance as a rough proxy for navagibility.

The brief asked how I would reproduce a map like the one it showed, so I drew two. The first (`q2_observed.png`) is just the data as given, the facilities plus the three real pipelines. It is sparse, which is the whole problem. The second (`q2_inferred.png`) is the reconstruction, the real pipelines drawn solid and my inferred sea lanes and barges drawn dashed, with opacity set by confidence so you can see what is trusted and what is not.

The payoff is the comparison between the two maps. With only the observed data just one cracker (Moerdijk) is reachable, because it is the only one sitting on a real pipeline. After inference all five crackers connect up, including the inland Chemelot complex which gets fed by a barge. And nothing illegal appears, no ethylene barges and no sea lanes to inland sites.

Run `python run_q2.py` to produce aplot of observed pipelines and then infered edges.

### Q3 - Scenario analysis

The brief says to treat the solver as a black box. The interesting question is not how the solver works, it is where the "what-if" lives and how I feed it.

The key decision is that a shock is not a change to the data or to the graph. It is an overlay on the input I hand to the solver, expressed as capacity. To take a facility offline I set the capacity of its units to zero. To make a region or a mode impassable I set the capacity of the affected edges to zero. The raw data and the graph topology never change.

To model different scenarions I chose to do this in the solver for a few reasons. I would not put scenarios in the data, this is because the data is a ground truth. As you data sources improve over time, they may change but I think conecptionally it is clean to only store things you know to be true. The second option to model scnarios in the graph builder also does not make sense to me. The purpose of this layer is to transform the data from a raw format into a usable format. This means structuring it to make it easy to query or condifying uncertainty. Applying these changes in the imput to the solver is the cleanest place to have these scenarios, it is where hypothetical scenarios make the most sense and do not polute other functions of the system


To compare a baseline against a shock I just run the solver twice. The baseline is solve(input), the shock is solve(overlay(input)), and then I diff the two. I also chose to define the output as well as the input, not just the flow on each edge but whether each cracker actually got supplied. This means the answer to "which cracker starved" falls straight out of the diff.

On the sample the baseline supplies all five crackers. Taking the Antwerp port offline is localised, it starves the three crackers fed from the Antwerp barge. Closing the Rhine to barges is systemic, it starves four of the five. The only survivor is Moerdijk, because it is the one cracker fed by real observed pipelines rather than an inferred barge. So my biggest shock is the one that leans on my weakest data, which is worth keeping in mind.

`run_q3_map.py` draws the three runs side by side (`q3_shocks.png`). Edges that stop carrying material go grey and dotted, and crackers that lose supply are greyed out with a cross, so you can see at a glance which shocks are local and which are systemic.