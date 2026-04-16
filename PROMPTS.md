# Prompts Used In This Build

This file captures the user prompts from the working session that led to the final app.

## Prompt Log

1. `hey friend! im back again with another school assignment. I have project instructions here and a sample solution already of what we are tasked to build. since it's streamlit, how do I run it locally? so I can see what the site looks like? do I have to run the code and it'll boot on a local server? if so, is it possible to make edits and changes in real time or do I have to run the code in full each time I make a change?`

2. `yes please. also get familiar with the code and the project instructions. we'll be working closely together on this`

3. `done! so this is what I want to do next. I need to build on top of this example solution and I want to make it way better. but first, I want to test some of those changes in a smaller setting before commiting them to what would basically be a fork of example_solution.py. what would be the best way to start to do that? specifically the first task I want to tackle is changing the visualization charts.`

4. `yes please~!`

5. `can we switch the filters to drop down selection?`

6. `so the filters also need the option to allow me to select more than one item at a time. almost like a checkmark next to them`

7. `lets try using st.pills`

8. `are we able to change up the color of the selected pills? they currently light up red, but I'd like for them to light up green. also, the entire dashboard is in dark mode and I'd like to switch to a more modern white and blue setup`

9. `the app looks horrible now man, and the the pills are still red. can you undo everything?`

10. `ok! let's work on the charts now. for the sales over time chart, lets change the way the x axis title is showing now. when it's quarter, lets format it like "2014-Q1" and sit the label on an angle instead of vertical so it's easier to read. when the grouping is Monthly, let's format like "2014-01" and also put the label on an angle`

11. `alright now let's work on the bar chart. lets also sit the labels at 35 and can we create some consistency in the legend colors between both charts? so the regions are the same color on both, and do the same for all the other categories. let's also set a default for the time series graph so that everytime it loads for the first time, it will load to this: area graph compared by region. and for the bar chart lets default it to region as well`

12. `alright, I think we're ready to start merging our chart and pill work with the main example solution. whats the best path forward for this? start a new app.py file that begins to merge them both? pick the best path forward and start doing the work and then just ask for my review`

13. `running the app died here: ... can you fix this? my keys are in the .env file`

14. `I plan to deploy this once we're done. what would be the best way to plan for shipping with my keys?`

15. `yes please!`

16. `awesome! let's change the functionality of the "Chart Insights with AI" button. currently, it'll just run a function of sending the graph to openai and having it some llm give back a response. everytime you click the button, it will generate a new response. I want some way to cache and manage responses we've received so we aren't burning tokens each time we hit the button. also the way it happens now is in a pop window which im not the biggest fan of. could there be a better more user friendly way to show responses and also manage the history of responses received?`

17. `thats so great! now, can we have a radio button under both charts and name it "Generate AI Insight for this Chart" ? currently we only have it under the area graph. also, on the bottom of the page, we have this "quick insights" module. can we put that up on the same plane as the two charts? have it be a slim module on the left hand side`

18. `the "top items in breakdown" slider seems to be pretty useless. please remove it and all its dependencies. also rearrange the chart modifiers "time-series style, time grain, etc" to be more intuitive to the chart they change. currently they are poorly formatted and not easy to know which controls which chart without poking them all`

19. `can we brainstorm what it would take to turn this into a universal upload tool? as in: upload any data set and we'll make these 2 charts and analysis for you. I don't think we can do it cleanly on our own, we'd have to leverage openai api to inject some smartness into it but im curious how we'd do it. i think we would have to create "placehoders" for the x and y axis, have openai interpret the data we uploaded and help us map that data back to our "placeholders" at least i think so, but tell me if there's a better way`

20. `yes, lets give it a shot in a separate playground because i like where our app is now and I dont want to botch it`

21. `can we open it up to files other than csv? particularly excel files`

22. `I encountered the following two errors in testing: ... other than that, this works great!`

23. `test passed! all is in working order`

24. `lets add in the openai assisted stuff. if we can get this in a super good working place, id like to ship the version that takes in any file. for the openai piece when asking for help, i think it'd be best to be the most concise we can be to minimize token usage. maybe sending the head and tail of the data set only, 10 of each for 20 rows max for help`

25. `I switched the model to nano and after testing quite a bit, I think we should default to implementing the AI chosen set. It works so much better than the manual picking. maybe the flow should be:
load data > parse head and tail (20 samples) > ask openai for help > use the suggested mappings > allow user to modify if they want`

26. `awesome! it works great. now let's get rid of some kinks. "Mapping Strategy" subheader is redundant, lets remove it. "Refresh AI Mapping" is redundant lets remove it. "current default:" can also be removed and instead let's put what openai model produced the results and lets place it under "Suggested Mapping"

if AI mapping fails for whatever reason, lets do a single retry and if that retry fails, let's fall back to manual mapping.`

27. `in our logic, what is the difference between category dimension and a group dimension?`

28. `yes that would be much more helpful! can we also arrange the dropdowns to be in this order: Time, Group, Category, Primary, Secondary`

29. `alright I did some minor tweaks and I love where it is now. one other thing to ask: how big of a lift would it be to do something like allow the user to make a request or modification to the dataset they uploaded? I feel like that begins to cross the line into relying on AI and burning through tokens in our app. but the case in my mind is if a user uploaded data that only had day level data, but they want to group the timeseries to quarter or year`

30. `lets add in the changes you were mentioned that dont need AI at all. those sound incredibly useful and might be more than enough actually. after that we can call it done and move on to merging`

31. `looks good! I also see that in app.py we actually already had "chart style" "time grain" "compare by" already! so lets just merge the two apps now. can you merge it into an entirely new file called app_2.py ? this way I can run both side by side and A/B test them`

32. `app 2 is great! but we're missing a lot of polish we had in app.py. here's the list of what we still need:

* all the filters from the left pane. I suppose now we can auto populate the pills in from the fields we end up using in time-series grouping. we should rename them to be more helpful as well like "time-series filter" and "bar chart filter"
* we currently have the "detected schema profile" which is fine but should remain hidden always. we also need to bring back in the "preview data"
* Metric to visualize needs to come back so we can choose between primary or secondary metric
* Quick Insights field should come back
* the totals and sums under preview data should come back however you think will work best in our new universal approach`

33. `this is amazing! lets just do these last couple changes and I think we're done my friend.

Time grain, Time-series chart style, and Metric aggregation should all sit right above the time-series chart like we had in app.py

Top categories in bar chart can sit right above the bar chart

let's change "Transformations" to be "Visualization Options" and also make is a smaller header.

"Metric to visualize" should sit above "Quick Insights"`

34. `ValueError: not enough values to unpack (expected 4, got 1) ...`

35. `we need to move this back to where it was here`

36. `that didn't fix it gang`

37. `still not fixed and I also realized you didn't make any changes at all in that last message you just sent. maybe this convo is running out of context window and you're starting to get frazzled. let me know and I can start a new chat`

38. `all the summary stats (total sales, total profit, rows, date span) need to sit in a row above the two charts. lets start there`

39. `amazing and everything is good to go. one last feature to add that we both forgot about. filtering the data set. either for nulls or zeros. we can also add an option for imputation maybe. I think the way that we drop down preview data we can do something similar called filter or modify data and therein we can let the user choose columns to filter (either nulls or zeros) or impute by using lightweight methods (nothing that needs heavy computing or validation like regression)`

40. `alright lets get ready to deploy this thing! can you do a final sweep of the folder, clean anything and everything up, make sure readme and requirements are gold and feel free to rename any files themselves`

41. `will my api key be in secrets once i deploy? meaning all the openai parts of our app will continue to work?`

42. `are you able to export the prompts I used across this chat?`

43. `yeah drop them into a prompts.md and have it just be the prompts I sent to you`
