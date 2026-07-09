from app.prompts.shot_types import SHOT_TYPES


SOCIAL_BODY_CONTINUITY_PHRASE = (
    "same natural sun-kissed skin tone as the reference image, full natural D-cup bust, feminine hourglass body, "
    "same waist-to-hip proportions, close creator-style framing with her body large in frame"
)

SOCIAL_CLOSE_FRAMING_RENDER_LOCK = """
SOCIAL CLOSE-FRAMING LOCK - NON-NEGOTIABLE:
REFERENCE IMAGE USAGE:
Use the reference image only for the creator's identity, face, hair, skin tone, body shape, and full natural D-cup bust.
Do not copy the reference image's setting, background, water, boat, dock, railing, trees, cabin, furniture, outfit, pose, lighting, or camera angle unless the written prompt explicitly asks for those exact elements.
The written prompt controls the scene, wardrobe, pose, lighting, and background.
If the prompt asks for a shower, bathroom, bedroom, hotel, couch, pool, city, beach, or any non-boat scene, do not include boat/lake/dock/marina details from the reference image.
Use tight creator framing unless the prompt explicitly asks for a wide environmental shot.
Use close-up, close-medium, waist-up, head-to-hips, head-to-upper-thigh, upper-thigh, or intimate seated close framing.
Keep the creator large in frame, with her face, upper body, torso, bust, waist, and hip angle treated as the main visual anchors.
Keep her full face and full head inside the frame, including forehead, hairline, and crown, with a small amount of breathing room above her hair.
Keep the camera close enough that her full natural D-cup bust, hourglass waist, reference skin tone, and recognizable facial identity are obvious.
Keep the background secondary. The environment may be visible, but it must not become the main subject.
Avoid distant full-body shots, tiny-subject compositions, wide room shots, wide bed shots, scenery-dominant lake/pool/landscape shots, or any framing where the room, water, furniture, or landscape is more visually important than the creator.
Avoid cropped-off forehead, cropped hairline, cut-off crown, missing top of head, or a composition that slices through her hair.
Do not crop out the body cues needed to preserve her D-cup bust, hourglass shape, reference skin tone, and recognizable facial identity.
Avoid visible phone/cellphone/selfie-device poses unless the prompt explicitly asks for a phone or mirror selfie.
Keep the result social-platform safe according to the selected Social Content Studio mode.
""".strip()

SOCIAL_EXPRESSION_FALLBACK_PHRASE = (
    "natural warm engaged facial expression with a subtle genuine smile that reaches her eyes"
)


def enforce_social_close_framing_lock(prompt):
    cleaned_prompt = (prompt or "").strip()
    if not cleaned_prompt:
        return ""

    if "SOCIAL CLOSE-FRAMING LOCK" in cleaned_prompt:
        return cleaned_prompt

    return f"{cleaned_prompt}\n\n{SOCIAL_CLOSE_FRAMING_RENDER_LOCK}"


def normalize_social_prompt_continuity(prompt):
    cleaned_prompt = (prompt or "").strip()
    if not cleaned_prompt:
        return ""

    prompt_lower = cleaned_prompt.lower()
    required_terms = [
        "skin tone",
        "d-cup",
        "hourglass",
        "waist-to-hip",
        "close",
    ]

    if all(term in prompt_lower for term in required_terms):
        continuity_prompt = cleaned_prompt
    else:
        cleaned_prompt = cleaned_prompt.rstrip(" ,.")
        continuity_prompt = f"{cleaned_prompt}, {SOCIAL_BODY_CONTINUITY_PHRASE}"

    expression_terms = [
        "smile",
        "laugh",
        "grin",
        "playful",
        "happy",
        "excited",
        "warm expression",
        "flirty",
        "mischievous",
        "confident gaze",
        "engaged",
    ]

    if any(term in continuity_prompt.lower() for term in expression_terms):
        return continuity_prompt

    return f"{continuity_prompt.rstrip(' ,.')}, {SOCIAL_EXPRESSION_FALLBACK_PHRASE}"


def build_shot_type_context():
    formatted_shot_types = "\n".join(
        f"- {shot_type}"
        for shot_type in SHOT_TYPES
    )

    return f"""
SHOT INTELLIGENCE:
Use a natural mix of universal photography shot types to create visual variety.

Suggested shot types:
{formatted_shot_types}

IMPORTANT:
- These are not hard rules.
- Do not repeat the same shot type too often.
- Adapt shot types dynamically to the user's tags.
- Use them to improve pose variety, framing, camera distance, body orientation, and composition.
"""


def build_chatgpt_prompt(
    prompt_count,
    user_request,
    generation_mode,
    platform_mode,
    spice_level,
):

    shot_type_context = build_shot_type_context()

    universal_style = f"""
Photorealistic AI creator photography.

The images should feel:
- realistic
- sharp
- detailed
- high quality
- creator-content ready
- visually intentional
- made for high engagement
- strong enough for Nano image generation

User tags/request:
{user_request}

Creative mode:
{spice_level}
"""

    creative_director_rules = f"""
CREATIVE DIRECTOR MODE:

The user is NOT writing full prompts.
The user is only providing creative signals.

Your job is to become an AI Creative Director.

IMPORTANT:
Minimal input must produce MAXIMUM intelligent creativity.

Creative Director behavior:
- Preserve roughly 70-80% of the user's idea and aesthetic
- Add roughly 20-30% intelligent expansion
- Invent realistic scene details
- Invent realistic environments
- Invent realistic camera framing
- Invent realistic lighting
- Invent realistic mood
- Invent pose ideas
- Invent composition
- Invent creator-style scenarios
- Turn short keyword inputs into complete Nano-ready image prompts
- Build full visual scenes instead of sparse prompt fragments

Treat user tags as CREATIVE SIGNALS rather than rigid repeated objects.

Examples:

cowgirl hat, desert

does NOT require:
- identical hat usage in every image
- identical outfits
- identical styling
- identical scene setup
- identical poses
- identical camera angles

Instead intelligently preserve:
- overall aesthetic
- creator vibe
- visual theme
- emotional feel
- core user intent

while varying:
- styling
- accessories
- activities
- environment details
- pose concepts
- camera framing
- visual hooks
- content scenarios
- realistic objects
- micro-behaviors
- body orientation
- background details
- social-post composition

Think like:
- photographer
- creator content producer
- creative director
- visual marketing director
- Nano prompt specialist

Do NOT simply repeat keywords.
Do NOT create duplicate ideas.
Do NOT create sparse prompts.

The batch should feel like:
{prompt_count} different posts from the same creator brand.

User creative tags:
{user_request}

MULTI-LINE USER TAG RULE:

If the user creative tags contain multiple lines,
each line is a separate image concept.

Treat each line independently.

Do NOT merge multiple lines together.
Do NOT blend multiple lines into the same prompt.
Do NOT treat all lines as one giant tag pool.

Generate exactly one prompt per line when multiple lines are provided.

Prompt 1 should be based on Line 1.
Prompt 2 should be based on Line 2.
Prompt 3 should be based on Line 3.
Continue this pattern until {prompt_count} prompts are created.

If fewer lines than {prompt_count} are provided,
create additional prompts by intelligently expanding the same creator brand and vibe.

If more lines than {prompt_count} are provided,
use only the first {prompt_count} lines.

Each final prompt should primarily follow its corresponding line's concept while expanding it into a complete Nano-ready image prompt.
"""

    if generation_mode["key"] == "variety_batch":

        mode_rules = """
CREATIVE FLOW:
VARIETY MODE

PURPOSE:
Generate multiple different content ideas from the user's tags.

This is discovery mode.

The images should NOT feel like one continuous photoshoot.
The images should NOT require continuity.
The images should feel like different strong options based on the same user idea.

RULES:
- Create completely different image ideas
- Keep the user's core tags/intention present
- Treat tags as creative signals, not rigid repeated objects
- Vary setting, pose, outfit styling, lighting, camera angle, framing, activity, mood, and body orientation
- Use creative expansion freely when it fits the user's idea
- Avoid duplicate-looking prompts
- Each image should work as its own standalone content option
- Prioritize variety over continuity
- Prioritize close-medium creator framing over distant full-body scenery
- The woman should usually fill most of the frame
- Use waist-up, upper-thigh, close-medium, or intimate creator-photo crops often
- Avoid far-away landscape-first images unless the user clearly asks for scenery
- Background should support the subject, not dominate the image
- Stronger images should feel close, sharp, and phone-camera intimate
- Make every prompt feel like a separate social post
- Give every prompt a different visual reason to exist
- Build fully descriptive creator scenes, not short pose descriptions

Example:
If the user enters "bikini, beach", do NOT make 10 versions of the same beach pose.
Create varied bikini/beach-inspired ideas such as mirror selfie, shoreline walk, poolside lounge, beach chair pose, sunset water-edge shot, close portrait, candid walking shot, low-angle hero shot, balcony view, and towel-side creator moment.
"""

    elif generation_mode["key"] == "photoshoot_set":

        mode_rules = """
CREATIVE FLOW:
PHOTOSHOOT MODE

PURPOSE:
Continue one selected image as the same photoshoot.

This is expansion mode.

LOCK:
- same outfit
- same user-requested or selected-shot setting
- same user-requested or selected-shot environment
- same lighting
- same vibe
- same camera style
- same creative concept
- do not inherit unrelated background details from the identity reference image

VARY ONLY:
- pose
- camera angle
- framing
- crop
- expression
- perspective
- hand placement
- posture
- distance from camera
- eye contact
- body orientation

Do NOT change the outfit.
Do NOT change the user-requested or selected-shot setting.
Do NOT create unrelated scenes.
If the identity reference image contains a boat, lake, dock, railing, cabin, or outdoor natural-water background, do not copy those elements unless they are part of the user-requested or selected-shot setting.

The images should feel like multiple strong shots from the same professional creator shoot.
"""

    elif generation_mode["key"] == "story_sequence":

        mode_rules = """
CREATIVE FLOW:
STORY MODE

PURPOSE:
Turn one selected image into a visual timeline.

This is progression mode.

RULES:
- Keep continuity
- Keep same subject
- Keep same outfit direction
- Keep the same user-requested or selected-story environment
- Keep same overall vibe
- Do not inherit unrelated background details from the identity reference image
- Create a sequence of connected moments
- Each image should feel like the next beat in the same story
- Progress action naturally from image to image
- Vary framing as the story evolves
- Keep the visual timeline believable

Example:
For a beach image, create a progression such as arriving, walking toward water, standing at shoreline, sitting on towel, entering water, candid close-up, sunset ending.
"""

    elif generation_mode["key"] == "nsfw_evolution":

        mode_rules = """
CREATIVE FLOW:
NSFW EVOLUTION MODE

PURPOSE:
Automatic strong NSFW progression from the requested starting state.
Optimized for adult content with natural erotic escalation.

RULES:
- Start close to the reference identity/body/coverage state, while following the user's requested setting if one is provided.
- Progress sensuality and explicitness gradually across the full batch.
- Natural clothing removal progression (partial → topless → sliding panties down → full nude).
- Move into intimate self-touch: hands on breasts, squeezing, rubbing over clothing, fingers on clit, fingering, masturbation poses.
- Do not copy the identity reference image's boat, lake, dock, railing, room, floor/walls/background/furniture, lighting, or props unless the user explicitly asks for same-setting continuation.
- If the user asks for shower, bathroom, bedroom, hotel, couch, pool, city, beach, or any non-boat scene, do not include boat, lake, dock, marina, railing, or outdoor natural-water elements from the reference image.
- Never revert to more clothing than previous steps.
- Maintain perfect continuity of face, hair, body, reference skin tone, and D-cup bust in every prompt.
- Use natural, sensual, private-creator-moment language.
- Vary angles, pleasure expressions (eyes closed in ecstasy, biting lip, moaning face, arching back, etc.).
- Favor close, intimate framing that emphasizes body and action.
- Increase explicitness step by step across the sequence.

MANDATORY:
- The batch should feel like one continuous private NSFW moment evolving in real time.
- Explicit intimate acts are expected and should be described directly when the progression reaches that stage.
"""

    else:

        mode_rules = """
CREATIVE FLOW:
DEFAULT VARIETY MODE

Create varied, photorealistic content ideas from the user's tags.
"""

    if spice_level == "Social Safe":

        spice_rules = """
CREATIVE MODE:
SOCIAL SAFE

PRIMARY GOAL:
Lifestyle appeal.

This mode is for:
- lifestyle
- travel
- beauty
- fashion
- friendly creator content
- polished social-media content
- mainstream-safe attractiveness

The images should feel attractive and visually engaging,
but the tone should be more lifestyle-driven than sex-appeal-driven.

CONSTANT PRIORITIES:
- lifestyle content
- beauty
- confidence
- realism
- natural attractiveness
- fashionable styling
- friendly energy
- polished social-media appeal
- tasteful visual appeal
- safe creator-content aesthetics

VARIABLE ELEMENTS:
- outfit styling
- activity
- environment
- mood
- pose
- camera angle
- framing
- lighting
- expression
- lifestyle objects
- realistic surroundings

IMPORTANT:
- Keep everything social-media safe
- No nudity
- No explicit sexual content
- Avoid adult-platform language
- Avoid excessive body emphasis
- Use attractiveness through lifestyle, confidence, fashion, lighting, and composition
- The image should feel like it could fit Instagram, X, or mainstream social content
"""

    elif spice_level == "Spicy":

        spice_rules = """
CREATIVE MODE:
SPICY

PRIMARY GOAL:
SFW sex appeal for male audience attention.

This mode is NOT lifestyle-first.

This mode should create highly descriptive, male-attention optimized creator images while still remaining social-media safe.

The images should feel:
- visually magnetic
- flirtatious
- confident
- body-aware
- high-engagement
- creator-platform ready
- strongly appealing to men
- polished but natural
- realistic enough to look like a real creator post

IMPORTANT:
The user wants MINIMAL effort.

The user provides signals only.

Examples:
- bikini, apartment
- cowgirl hat, desert
- Google Pixel phone, luxury apartment
- oil, beach
- short shorts, kitchen
- lingerie, bedroom
- crop top, car
- tight dress, city night

The AI Creative Director invents the remaining 90-95%.

DO NOT create sparse prompts.

Bad:
woman standing in desert

Bad:
woman wearing bikini in apartment

Bad:
woman sitting on bed

Good:
standing in a modern luxury apartment at night taking a mirror selfie with a phone, body angled away from the mirror while looking back over her shoulder, fitted minimal swimwear styling, soft indoor lighting mixed with city lights through floor-to-ceiling windows, marble kitchen island and bar stools visible behind her, warm skin glow, realistic mobile-photo sharpness, strong curves-focused composition, detailed creator-content atmosphere

Good:
walking beside an old desert truck at golden hour while adjusting a cowgirl hat with one hand, body angled slightly toward the camera with confident eye contact, fitted western-inspired outfit with short denim styling, loose hair moving in the wind, warm sunlight wrapping around skin and clothing, distant canyon textures and subtle dust movement in the background, slight low-angle smartphone perspective, strong body-leading composition, natural male-attention creator energy

SPICY MODE MUST PRIORITIZE SEX APPEAL THROUGH VISUAL DESIGN.

Use strong visual attraction through:
- natural flattering composition
- body-leading framing
- over-the-shoulder angles
- low-angle camera perspective
- fitted clothing
- short cuts where appropriate
- skin visibility where appropriate
- warm skin glow
- confident eye contact
- playful expression
- posture curves
- back-turned or three-quarter body angles
- mirror/selfie compositions
- phone-content realism
- movement in hair and clothing
- flattering silhouettes
- natural body proportions and flattering framing
- candid but intentional creator energy

Do NOT make Spicy mode generic lifestyle.
Do NOT soften Spicy into normal travel/fashion content.
Do NOT make the subject look passive or boring.
Do NOT create bland standing poses.

NANO SCENE INTELLIGENCE:
Nano responds strongly to highly descriptive visual scenes.

Every Spicy prompt should include:

1. SUBJECT CONTINUITY:
- same woman from reference image
- identical face, hair, and body
- consistent creator identity

2. SEX-APPEAL COMPOSITION:
- body angle
- posture
- camera distance
- curves-focused framing
- confident eye contact or over-the-shoulder glance
- flattering silhouette
- strong visual hook

3. SCENE:
- specific location
- realistic surroundings
- environmental objects
- background depth
- believable creator setting

4. MICRO-BEHAVIOR:
- what she is doing in the moment
- small natural action
- realistic movement
- interaction with clothing, hair, phone, object, or environment

5. CAMERA:
- camera distance
- camera angle
- phone/selfie/mirror/low-angle/candid perspective when appropriate
- framing and composition

6. LIGHTING:
- warm skin glow
- golden light
- indoor ambient light
- city lights
- soft highlights
- realistic shadows

7. ENVIRONMENT DETAIL:
- furniture
- windows
- reflections
- vehicles
- landscape detail
- architecture
- water movement
- dust movement
- fabric movement
- realistic textures

Build COMPLETE creator moments.

Do NOT only describe a pose.
Do NOT only describe an outfit.
Do NOT only describe a location.

The final prompts should feel like:
- high-performing creator content
- male-attention optimized social posts
- polished but natural photos
- candid but intentional
- visually rich Nano-ready scenes

SCENE BUILDING PRIORITIES:

Invent realistic details based on the user's tags.

Apartment / luxury apartment signals may include:
- modern kitchen island
- marble counters
- city lights through large windows
- floor-to-ceiling glass
- couch
- bar stools
- modern furniture
- mirror selfie setup
- phone in hand
- night interior lighting
- reflections in glass
- body angled toward mirror
- over-the-shoulder glance
- warm skin glow

Beach / pool / water signals may include:
Examples are inspiration only.

Do NOT repeatedly select the first few examples.

Actively rotate through different concepts, activities, and camera perspectives.
- shoreline textures
- beach towels
- umbrellas
- waves
- wet sand
- reflections
- resort pool furniture
- sunset water glow
- sunglasses
- drink in hand
- wind movement
- body angled toward camera
- low-angle towel-side framing
- fitted swimwear styling

Desert / western / cowgirl signals may include:
- canyon textures
- old pickup truck
- weathered fence
- dust movement
- dry riverbeds
- rock formations
- sunset depth
- boots
- hat adjustment
- roadside travel mood
- wind in hair
- fitted western styling
- over-the-shoulder framing
- low-angle body-leading perspective

Kitchen / home signals may include:
- countertops
- refrigerator light
- cabinets
- coffee mug
- phone in hand
- morning window light
- modern home details
- counter-edge pose
- casual fitted outfit
- mirror or phone-content framing
- warm indoor light

Car / garage / street signals may include:
- open car door
- dashboard light
- city street glow
- parking garage depth
- reflections
- leaning near vehicle
- candid roadside moment
- stepping out of car
- fitted outfit
- three-quarter body angle
- confident glance

Bedroom / indoor signals may include:
- soft bedding
- window light
- mirror reflection
- nightstand details
- warm lamps
- casual lounging moment
- fitted or minimal outfit styling where appropriate
- strong but safe creator framing
- over-the-shoulder pose
- warm skin glow

Gym / athletic signals may include:
- mirror selfie
- gym lighting
- water bottle
- equipment depth
- fitted athleticwear
- confident posture
- post-workout glow
- body-leading mirror composition
- strong waist/leg emphasis
- candid creator energy

MICRO-BEHAVIOR PRIORITIES:

Avoid static posing.

Create male-attention creator moments such as:
- adjusting hair while looking toward camera
- fixing sunglasses with confident eye contact
- touching hat while body is angled toward camera
- looking over shoulder
- holding phone for mirror selfie
- taking casual selfie
- laughing naturally while turned slightly away
- leaning into frame
- turning toward the camera
- resting one hand on hip
- adjusting jacket or shirt
- holding a drink
- sitting on counter edge where appropriate
- stepping out of a vehicle
- leaning against railing
- glancing back mid-step
- brushing hair away
- walking naturally with body-leading composition
- seated three-quarter pose
- standing with back partially turned toward camera
- relaxed pose with strong posture curves
- candid reaction moment

REALISM / CAUGHT-IN-THE-MOMENT PRIORITIES:

TOP PRIORITY:
The image should feel like a REAL creator accidentally captured
during a natural moment rather than a professional photo shoot.

The viewer should feel:

"I caught this moment"

NOT:

"she stopped and posed"

Use realism through:

- candid timing
- imperfect posture
- natural weight shifting
- casual body positioning
- small facial asymmetry
- relaxed expressions
- slight movement blur where natural
- hair partially out of place
- clothing movement
- natural hand placement
- partially unfinished actions
- mid-motion behavior
- casual eye behavior
- looking away from camera sometimes
- glancing toward camera instead of staring
- slight smile
- soft expression
- natural breathing posture
- uneven shoulder positioning
- relaxed spine positioning
- sitting naturally
- leaning naturally
- body resting against environment
- captured between actions
- natural phone-camera feeling

GOOD CAUGHT-IN-MOMENT EXAMPLES:

- brushing hair behind ear mid-conversation
- looking back after hearing someone call her name
- laughing during movement
- adjusting outfit naturally
- sitting while shifting posture
- looking toward sunset
- glancing at phone
- leaning against railing casually
- sitting on rocks while relaxing
- walking while looking sideways
- mid-step movement
- relaxing on couch
- fixing hat while distracted
- smiling softly while turning toward camera
- resting elbows naturally
- shifting weight onto one leg

AVOID:

- runway model poses
- centered fashion poses
- perfect symmetry
- exaggerated arching
- extreme eye contact in every image
- standing still for camera
- hero shots
- fashion campaign energy
- magazine cover energy
- overly polished studio feeling

REAL CAMERA FEEL:

TOP PRIORITY:

The photo should feel like a real creator casually took the image.

Use:

- smartphone camera realism
- handheld feeling
- casual framing
- slight camera tilt sometimes
- slightly imperfect crop
- realistic social-media composition
- natural depth of field
- occasional foreground objects
- realistic phone-camera sharpness
- camera feels unnoticed
- natural subject placement
- image captured between moments
- slight motion where natural
- candid timing
- authentic social-media feeling

Avoid:

- centered fashion framing
- magazine composition
- studio energy
- perfectly symmetrical placement
- runway photography
- professional campaign feeling

CAMERA PRIORITIES:

Use strong creator-style camera design:
- smartphone-content perspective
- mirror selfie composition
- slight low-angle framing
- body-leading composition
- over-the-shoulder perspective
- three-quarter body framing
- environmental framing
- close portrait variation
- candid framing
- depth layering
- foreground/background separation
- realistic camera feel
- mobile-photo sharpness
- natural lens behavior
- believable social-media crop
- strong subject-background separation

VISUAL HOOK RULES:

Use attraction through creator-content psychology:

- body-leading composition
- smartphone creator-photo realism
- low-angle smartphone framing
- over-the-shoulder glances
- close-medium framing
- foreground depth
- asymmetrical posture
- natural weight shifts
- movement in hair
- movement in clothing
- environmental interaction
- candid creator energy
- "caught in the moment" feeling
- natural posture curves
- realistic handheld camera feel
- warm skin glow
- subtle skin highlights
- natural depth of field
- perspective variation
- dynamic body orientation
- natural motion during walking or movement

HIGH ENGAGEMENT VISUAL ACTIONS:

Randomly vary:

- looking back over shoulder while walking away
- adjusting bikini strap naturally
- brushing wet hair back with one hand
- leaning into camera slightly
- shifting hips while glancing sideways
- mid-step walking movement
- resting elbows naturally on counter
- leaning against window while turning toward camera
- holding phone lower than eye level
- lifting sunglasses slightly
- sitting while shifting posture
- stretching naturally
- adjusting hair while distracted
- sitting sideways with torso turned toward camera
- stepping out of shallow water
- entering a room mid-motion
- glancing at reflection
- sitting on edge of furniture naturally
- walking while looking toward something off-camera
- leaning on one hip casually
- reaching toward camera slightly
- looking back after hearing something
- partially turning body toward camera
- shifting weight naturally
- fixing loose hair while smiling softly
- natural mirror selfie movement
- walking selfie movement
- candid phone movement
- relaxed body shifts

SCROLL STOPPER COMPOSITION:

Prioritize:

- close-medium framing
- foreground body depth
- camera near subject
- body closer to camera than background
- perspective compression
- layered framing
- environmental depth
- slight camera tilt
- strong foreground/background separation
- low-angle perspective
- asymmetrical composition
- body-leading visual flow
- realistic smartphone lens feeling
- intimate creator framing
- realistic handheld phone perspective
- natural perspective exaggeration
- foreground emphasis
- dynamic visual depth
- foreground body closer than face occasionally
- perspective emphasis on movement
- natural lens depth
- body entering frame partially
- cropped candid framing
- not every image should show full body

CAMERA STYLE PRIORITY:

Images should feel like:

- creator phone content
- Instagram creator photography
- candid lifestyle moments
- handheld realism
- realistic social media photography
- close visual hooks
- mobile camera sharpness
- dynamic composition
- creator selfie realism
- casual luxury lifestyle photography
- social-first content
- natural creator energy

NOT:

- fashion catalog
- studio photography
- magazine posing
- professional model shoots
- centered body placement
- perfect symmetry
- static standing poses
- runway photography
- stiff posing
- corporate photography
- flat composition
- lifeless framing

AVOID:

- repeated towel poses
- repeated sitting poses
- repeated camera heights
- repeated body orientation
- repeated framing
- repeated environments
- same camera distance
- same visual hook
- same object placement
- repeated selfie angles
- repeated room layouts
- repeated mirror shots
- repeated body positioning

IMPORTANT:

The viewer should immediately feel:

"I caught a real creator moment"

before noticing attractiveness.

Prioritize:

- visual hooks
- camera psychology
- natural movement
- creator realism
- engagement-focused composition
- scroll-stopping framing
- realistic perspective
- natural visual tension

STYLING PRIORITIES:

Use visually flattering creator wardrobe choices while staying social-media safe.

May intelligently vary:

- fitted casualwear
- creator-inspired outfits
- layered clothing
- modern social-media fashion
- flattering silhouettes
- fitted tops
- crop tops where appropriate
- fitted tanks
- tied shirts
- oversized shirts worn in a flattering way
- denim jackets
- lightweight jackets
- fitted dresses
- short cuts where appropriate
- swimwear where appropriate
- athletic-inspired looks
- vacation-inspired looks
- western-inspired fitted styling
- minimal but safe styling where appropriate

IMPORTANT:
User outfit tags are signals, not strict uniforms.

If the user says "cowgirl hat, desert":
- keep the western/desert creator aesthetic
- lean into body-leading angles, fitted styling, confident expressions, and warm skin glow
- do not force the exact same hat placement in every image
- do not force the same shirt and shorts in every image
- vary styling while preserving the theme

If the user says "bikini, apartment":
- keep the bikini/apartment concept
- lean into mirror selfie, phone selfie, kitchen island, city-window, couch area, night lighting, over-the-shoulder angles, and strong body-leading composition
- do not make every image the same standing mirror selfie

If the user says "Google Pixel phone, luxury apartment":
- include the phone naturally where useful
- lean into high-engagement mirror/selfie creator framing
- vary selfie, mirror, city-window, kitchen island, couch, hallway, and night-light scenarios
- do not repeat identical phone placement

VARIETY RULES:

Across Variety Batch prompts, strongly vary:
- sex-appeal framing
- body orientation
- activity
- environment
- outfit styling
- emotional expression
- scenario
- camera angle
- framing
- visual hooks
- perspective
- micro-behavior
- object interaction
- lighting source
- background details
- camera distance

Do NOT repeat:
- same pose
- same framing
- same activity
- same object placement
- same camera distance
- same scenario
- same emotional expression
- same outfit combination
- same camera angle
- same background setup
- same lighting setup
- same body orientation
- same micro-behavior

FACIAL EXPRESSION AND PERSONALITY RULES:

Every prompt must give her a visible, emotionally alive facial expression.
Do not default to blank, neutral, bored, monotone, mannequin-like, or emotionless expressions.

Most Social Content Studio prompts should make her feel warm, quietly happy,
playful, confident, approachable, flirty, or genuinely engaged.
Expressions must look candid and believable, not forced, fake, exaggerated,
plastic, or overacted.
Favor subtle eye warmth, relaxed cheeks, small asymmetry, natural mouth shape,
and in-the-moment micro-expressions over big posed smiles.

Use a varied expression palette such as:
- soft genuine smile that reaches her eyes
- subtle playful smile
- candid amused half-smile
- warm relaxed expression
- coy smile
- relaxed mischievous smirk
- candid laugh caught mid-moment
- confident friendly gaze
- playful raised eyebrow
- relaxed happy glow
- soft flirty smile

Avoid:
- forced smile
- fake grin
- overly toothy smile
- frozen pageant smile
- uncanny perfect smile
- exaggerated open-mouth acting
- dead eyes with a pasted-on smile

Vary the expression in every prompt.
Do not repeat the same facial gesture across the batch.
The goal is a creator with personality and life, not a beautiful but monotone subject.

The batch should feel like:
10 different male-attention optimized creator posts from the same creator brand.

Each prompt should feel like one clean creator moment.

Each prompt should give Nano:

- one scene
- one action
- one camera perspective
- one body orientation
- one lighting source
- one visual hook

Avoid stacking multiple competing ideas.

Avoid vague filler phrases unless supported by concrete visual details.

No nudity.
No explicit sexual acts.
No underage appearance.
Keep realistic photography.
Keep social-media safe while maximizing sex appeal.
"""

    else:

        spice_rules = """
CREATIVE MODE:
EXPLICIT

Explicit mode is coming later.
For now, behave like Spicy mode.
"""

    return f"""
I need a list of {prompt_count} high-quality image-to-image prompts.

These prompts always use the SAME reference image.

REFERENCE IMAGE USAGE:
The reference image is for identity/body continuity only.
Use it to preserve the same face, hair, natural sun-kissed skin tone, body shape, waist-to-hip proportions, and full natural D-cup bust.
Do not copy or inherit the reference image's location, background, boat, dock, railing, lake, natural water, trees, cabin, furniture, outfit, pose, lighting, camera angle, or props unless the user's written tags explicitly request them.
The user's tags and final prompt are the only source of truth for setting, wardrobe, nudity state, pose, activity, lighting, and background.
If the user asks for a shower, bathroom, bedroom, hotel, couch, pool, city, beach, or any non-boat scene, do not include boat, lake, dock, marina, railing, or outdoor natural-water elements from the reference image.

Every prompt MUST preserve:
- same woman
- same face
- same hair
- same natural sun-kissed skin tone as the reference image
- same body
- same identity from the reference image

BODY CONSISTENCY LOCK:
- preserve the exact overall body proportions shown in the reference image
- preserve the same recognizable body structure
- preserve the same overall body shape
- preserve the same overall body weight and physique
- preserve the same waist-to-hip ratio
- preserve the same hip width
- preserve the same thigh thickness
- preserve the same leg proportions
- preserve the same shoulder width
- preserve the same feminine hourglass silhouette
- preserve the exact same natural sun-kissed skin tone shown in the reference image
- maintain natural, even, photorealistic skin tone across visible skin without darkening it
- preserve realistic anatomy
- preserve photorealistic body structure
- maintain healthy feminine curves
- maintain consistent body proportions across every generated image

SKIN TONE CONTINUITY LOCK:
- every final prompt must explicitly include same natural sun-kissed skin tone as the reference image
- preserve the same reference skin tone across face, chest, arms, waist, hips, and legs when visible
- keep the skin tone natural, even, sun-kissed, and photorealistic
- do not intensify, deepen, darken, bronze, or over-tan her skin beyond the reference image
- do not make her pale, washed out, fair-skinned, or red-haired
- do not change her perceived ethnicity, underlying identity, or facial features while preserving skin-tone continuity

BUST CONSISTENCY LOCK:
- preserve the exact bust size shown in the reference image
- maintain full natural D-cup breast proportions
- maintain the exact breast size visible in the reference image
- preserve full breast volume and projection
- preserve natural D-cup fullness across every prompt
- maintain visible breast projection when clothing and pose allow it
- maintain a visibly full D-cup bust through social-safe styling, pose, framing, and fitted wardrobe
- maintain full upper breast volume
- maintain full lower breast volume
- maintain rounded natural breast shape
- maintain natural cleavage when visible
- keep bust proportions consistent across every prompt

SOCIAL OUTPUT BODY DESCRIPTION REQUIREMENT:
- Every final prompt must explicitly describe her same full natural D-cup bust.
- Every final prompt must explicitly describe her same feminine hourglass body shape.
- Every final prompt must preserve and visibly reference her same waist-to-hip ratio.
- Every final prompt must explicitly describe her same natural sun-kissed skin tone as the reference image.
- Every final prompt must keep the body description social-safe through clothing, styling, pose, camera angle, and framing.
- Do not make body preservation implicit only.
- Do not omit bust/body continuity from the final prompt text.
- Use SFW wording such as:
  - full natural D-cup bust
  - feminine hourglass silhouette
  - same curvy waist-to-hip proportions
  - same natural sun-kissed skin tone as the reference image
  - fitted social-safe styling that preserves her bust and body shape
  - visible D-cup bust projection through the outfit

SOCIAL FRAMING CONTINUITY REQUIREMENT:
- Favor the same closer creator-style framing that works in Premium Content Studio.
- Most prompts should use close-up, close-medium, waist-up, upper-thigh, or head-to-thigh framing.
- Keep her body large in frame, with the background supporting the scene rather than dominating it.
- Keep her full face and full head visible, including forehead, hairline, and crown, with a small amount of breathing room above her hair.
- Avoid distant full-body compositions unless the user specifically asks for a wide environmental shot.
- Avoid cropped-off forehead, cropped hairline, cut-off crown, missing top of head, or a composition that slices through her hair.
- Do not crop out the body cues needed to preserve her D-cup bust, hourglass shape, and reference skin tone.

Do NOT:
- reduce breast volume
- reduce breast projection
- reduce breast fullness
- make the subject smaller-busted than the reference image
- flatten the chest
- make the breasts look like a small B cup
- change body weight
- change waist size
- change hip size
- change thigh thickness
- change shoulder width
- change overall body proportions
- change chest-to-waist proportions
- change bust-to-waist proportions
- alter the recognizable silhouette of the reference image
- exaggerate anatomy
- create unrealistic proportions
- create artificial body distortion

{universal_style}

{creative_director_rules}

{shot_type_context}

{mode_rules}

{spice_rules}

PROMPT STRUCTURE:
Each prompt MUST start with:
"The exact same woman from the reference image with identical face, hair, same natural sun-kissed skin tone as the reference image, full natural D-cup bust, and feminine hourglass body,"

Every final prompt must include:
- full natural D-cup bust
- feminine hourglass body
- same waist-to-hip proportions
- same natural sun-kissed skin tone as the reference image
- social-safe fitted styling or framing that preserves her exact body shape
- a clearly described facial expression with happy, playful, excited, warm, confident, flirty, or genuinely engaged energy

Avoid reusing the same action, pose, or body orientation from previous generations.

If the user regenerates prompts, deliberately create new concepts rather than refining previous concepts.

Do not default to:
- looking over shoulder
- adjusting clothing straps
- shoreline standing poses
- walking along the beach

PROMPT DEPTH RULES:

Each prompt should read like a complete creator-photo concept.

Build prompts naturally in this order:

1. Environment
2. Action
3. Outfit interpretation
4. Body orientation
5. Camera behavior
6. Lighting
7. Background detail
8. Realism detail

Rules:

- ONE environment
- ONE action
- ONE camera style
- ONE dominant pose
- ONE lighting source
- 2–3 background details maximum

Examples:

modern apartment bedroom at night, taking a mirror selfie while adjusting hair, fitted crop top with tight shorts, body angled three-quarters away while looking back over shoulder, low-angle smartphone perspective, warm bedside lamp lighting, city lights and soft bedding visible, realistic creator-photo framing

modern kitchen during sunset, leaning casually against marble counters while holding phone naturally, fitted creator styling with shorts, one hip shifted naturally, arm-length phone perspective, warm window light, bar stools and reflections visible, realistic handheld camera feel

IMPORTANT:

IMPORTANT: Keep prompts roughly 1–2 sentences.

MAIN VARIETY FRAMING RULE:
For Variety Batch images, favor closer creator-photo framing:
- close-medium framing
- waist-up framing
- upper-thigh framing
- subject fills most of the image
- full face, full head, hairline, and crown stay clear with slight headroom above hair
- outfit and pose still visible
- background has depth but stays secondary

Avoid:
- distant full-body shots
- tiny subject in scenery
- wide landscape-first composition
- too much empty background

Do NOT create giant paragraph prompts.

Do NOT stack multiple actions.

Do NOT stack multiple camera styles.

Do NOT repeatedly say realism words.

The goal:

real creator content captured naturally
"""
